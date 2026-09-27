# ruff: noqa: E501  — system prompt examples must stay on one line per JSON output.
"""Prompt construction for the AI Gateway.

Command-aware: the system prompt is fixed, but the context block is built by
pre-fetching relevant DB state per domain heuristic on the input text. Keeps
the LLM able to answer "do I have apples?" without needing a separate read
tool round-trip.

Prompt improvement plan:
- Keep examples truthful to the backend contract. Do not teach argument shapes
  that the service layer will reject.
- Keep a small always-on example set focused on high-value behaviors:
  JSON shape, ask-vs-act decisions, id resolution from context, and
  domain-specific nested args.
- Prefer deterministic context over prompt verbosity. When a domain needs
  grounding, add or improve the context block before adding many more examples.
- Use read tools only when the user explicitly asks to search saved records;
  otherwise prefer answering directly from the provided CONTEXT.
- Move repeated edge-case behavior into rules when possible so examples stay
  compact and do not dominate token budget.
- Add prompt-contract tests whenever examples or rules encode assumptions that
  must stay aligned with backend validation.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.tools import tool_catalog
from family_assistant.grocery.services import list_on_hand_items, list_open_items
from family_assistant.lunch_plan.services import (
    list_family_members,
    start_of_week,
)
from family_assistant.lunch_plan.services import (
    list_week_entries as list_lunch_week_entries,
)
from family_assistant.meal_plan.options import match_recipes
from family_assistant.meal_plan.services import list_recipes
from family_assistant.meal_plan.services import list_week_entries as list_meal_week_entries
from family_assistant.memory.services import list_memories

BASE_PROMPT = """You are a household assistant for a single household with two adult users.
You translate natural-language commands into structured tool calls.

You MUST respond with a JSON object in this exact shape:
  {"tool_calls": [{"name": "<tool>", "args": {...}}], "reply": "<short message>"}

Rules:
- Only use tools listed in TOOL_CATALOG below. Do not invent tools or fields.
- Each tool's args MUST conform to its args_schema. Use only documented fields.
- Do NOT ask the user for fields that are optional in the schema. Use sensible
  defaults (i.e. omit the field) and proceed.
- DO ask a clarifying question (return tool_calls: [] with a question in reply)
  when the request is genuinely ambiguous: multiple matching records in CONTEXT,
  a required-by-schema field is missing from the input, the request conflicts
  with a hard restriction in household_memories, or an exercise activity name
  doesn't appear in the catalog. Better to ask than to guess.
- For pure questions ("do I have apples?", "what's for dinner?") answer from
  CONTEXT in the reply and set tool_calls to [].
- Use YYYY-MM-DD for dates. The current date is provided in CONTEXT.
- When referring to a family member or an existing grocery item, use the integer
  id shown in CONTEXT.
- CONTEXT.grocery_to_buy is the shopping list: things the household does NOT
  have yet. CONTEXT.on_hand is what they have (location kitchen or freezer).
  Never treat to-buy items as on hand.
- Keep reply short — one or two sentences.
"""

# Examples per domain; only the domains a request touches are sent (a small
# model does better with less to read, and copies examples less).
EXAMPLES: dict[str, str] = {
    "grocery": """
Input: "add milk and bread to the list"
Output: {"tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "milk"}, {"name": "bread"}]}}], "reply": "Added milk and bread."}
Note: items is a list of OBJECTS, each with a name. Don't flatten to a string.
      Don't ask for quantity/unit/category — they're optional.

Input: "mark eggs as purchased"  (CONTEXT.grocery_to_buy has Eggs id 41)
Output: {"tool_calls": [{"name": "grocery.mark_purchased", "args": {"item_ids": [41]}}], "reply": "Marked eggs as purchased."}
Note: use the integer id from CONTEXT.grocery_to_buy; do not pass item names to the tool.

Input: "I bought the milk"  (CONTEXT.grocery_to_buy has 2% milk id 12 and whole milk id 15)
Output: {"tool_calls": [], "reply": "I see two milk items — 2% (id 12) and whole (id 15). Which one did you buy?"}
Note: if multiple existing items match, ask instead of guessing.

Input: "mark eggs and milk as purchased"  (CONTEXT.grocery_to_buy has Eggs id 41 and Milk id 52)
Output: {"tool_calls": [{"name": "grocery.mark_purchased", "args": {"item_ids": [41, 52]}}], "reply": "Marked eggs and milk as purchased."}
Note: when multiple existing grocery items are named unambiguously, pass all matching ids in one item_ids list.
""",
    "meal": """
Input: "schedule dinner for Saturday"
Output: {"tool_calls": [], "reply": "What should we have for dinner Saturday?"}
Note: meal_plan.create_entry requires a title — don't guess one.

Input: "plan tacos for Friday"
Output: {"tool_calls": [{"name": "meal_plan.create_entry", "args": {"date": "2026-05-22", "meal_type": "dinner", "title": "Tacos"}}], "reply": "Planned tacos for Friday dinner."}
Note: infer meal_type from the meal named in the request when it is explicit.

Input: "what can I make for dinner with what we have?"  (CONTEXT.recipe_matches.ready has <recipe A>; recipe_matches.almost has <recipe B> missing <ingredient>)
Output: {"tool_calls": [], "reply": "<recipe A> — you have everything. <recipe B> works too if you pick up <ingredient>. Want me to plan one?"}
Note: recipe_matches is already computed against on_hand: "ready" has everything, "almost" lists what's "missing". Answer ONLY from the names actually in recipe_matches; never reuse names from these examples. If both lists are empty, say nothing matches what's on hand. "Suggest dinner ideas" or "what should we cook" means the same thing: suggest from recipe_matches, don't ask what they're in the mood for.

Input: "for next week's dinners, is the grocery list enough or do we need more?"  (CONTEXT.planned_meals lists this week's and next week's dinners by title and date; CONTEXT.recipe_catalog has their ingredients; CONTEXT.on_hand and CONTEXT.grocery_to_buy)
Output: {"tool_calls": [], "reply": "Next week you've planned <recipe A> and <recipe B>. <ingredients> are covered, but <other ingredients> aren't. Want me to add those to the grocery list?"}
Note: match each planned meal title to a recipe in recipe_catalog; an ingredient is covered if it's in on_hand or already in grocery_to_buy. Report what's not covered. If planned_meals has nothing for that week, say so and offer to suggest meals from recipe_matches. planned_meals and planned_lunches cover the current AND upcoming week — use each entry's date to focus on the week the user asked about. Offer to add the missing items rather than adding them unprompted.

Input: "add the ingredients for egg tacos to the list"  (CONTEXT.recipe_catalog has Egg Tacos: corn tortillas, eggs, cheese, salsa; CONTEXT.on_hand has Eggs and Cheddar Cheese)
Output: {"tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "corn tortillas"}, {"name": "salsa"}]}}], "reply": "Added corn tortillas and salsa — you already have eggs and cheese."}
Note: use the recipe's own ingredient names from recipe_catalog, skipping ones in on_hand or grocery_to_buy. Never add a vague item like "egg tacos ingredients".

Input: "plan butter chicken for Friday"  (CONTEXT.recipe_catalog has "Butter Chicken & Rice")
Output: {"tool_calls": [{"name": "meal_plan.create_entry", "args": {"date": "2026-05-22", "meal_type": "dinner", "title": "Butter Chicken & Rice"}}], "reply": "Planned Butter Chicken & Rice for Friday dinner."}
Note: when the request names a recipe that exists in recipe_catalog, use that recipe's exact name as the meal title.
""",
    "lunch": """
Input: "pack a lunch for <family member name> tomorrow"  (CONTEXT.family_members has <family member name> id 7; CONTEXT.recipe_catalog has lunch components grouped by note: Carb/Fruit/Veg/Treat)
Output: {"tool_calls": [{"name": "lunch_plan.create_entry", "args": {"family_member_id": 7, "date": "2026-05-21", "items": [{"name": "Grilled Cheese"}, {"name": "Apple"}, {"name": "Cookies"}]}}], "reply": "Packed grilled cheese, an apple, and a cookie for <family member name>."}
Note: compose a school lunch from recipe_catalog lunch components — typically one Carb plus a Fruit and a Treat. Respect any hard restriction in household_memories.

Input: "pack <family member name> a turkey sandwich and apple slices tomorrow"  (CONTEXT.family_members has <family member name> id 7)
Output: {"tool_calls": [{"name": "lunch_plan.create_entry", "args": {"family_member_id": 7, "date": "2026-05-21", "items": [{"name": "turkey sandwich"}, {"name": "apple slices"}]}}], "reply": "Planned <family member name>'s lunch for tomorrow."}
Note: items must be a list of objects; resolve the spoken family-member name to family_member_id from context.

Input: "pack lunch for tomorrow"  (CONTEXT.family_members has multiple family members)
Output: {"tool_calls": [], "reply": "Which family member is this lunch for?"}
Note: if a required field is missing and cannot be inferred safely, ask a clarifying question.

Input: "pack peanut butter for <family member name> tomorrow"  (household_memories has <family member name>: peanut hard restriction)
Output: {"tool_calls": [], "reply": "Memory says <family member name> has a peanut restriction. Want me to pick something else?"}
Note: when a request conflicts with a hard restriction in household_memories, ask instead of acting.
""",
    "exercise": """
Input: "log a 30 minute run for 2026-05-20"
Output: {"tool_calls": [{"name": "exercise.log_activity", "args": {"exercise_name": "run", "date": "2026-05-20", "duration_minutes": 30}}], "reply": "Logged a 30-minute run."}
Note: for read or write exercise commands, the exercise_name must refer to an existing catalog entry.

Input: "log bench press for today: 3 sets of 5 at 135"
Output: {"tool_calls": [{"name": "exercise.log_activity", "args": {"exercise_name": "bench press", "date": "2026-05-20", "sets": 3, "reps": 5, "weight": 135}}], "reply": "Logged bench press for today."}
Note: weighted exercises should use sets, reps, and weight.

Input: "log a 5k run today"
Output: {"tool_calls": [{"name": "exercise.log_activity", "args": {"exercise_name": "run", "date": "2026-05-20", "distance_km": 5}}], "reply": "Logged a 5K run for today."}
Note: distance-style activities should use distance_km when the request gives a distance.

Input: "log a workout today"
Output: {"tool_calls": [], "reply": "Which exercise — a run, a lift, something specific?"}

Input: "log <exercise name> for 45 minutes today"  (<exercise name> is not in the exercise catalog)
Output: {"tool_calls": [], "reply": "I don't see <exercise name> in the exercise catalog yet. Want to add it first in /exercise/catalog?"}
Note: if the exercise name is not in the catalog, ask instead of inventing or mapping it to something else.
""",
    "memory": """
Input: "remember that we always do meal prep on Sundays"
Output: {"tool_calls": [{"name": "memory.create", "args": {"subject_type": "household", "memory_type": "routine", "content": "We always do meal prep on Sundays."}}], "reply": "Got it."}

Input: "remember that <family member name> loves cucumbers"  (CONTEXT.family_members has <family member name> id 7)
Output: {"tool_calls": [{"name": "memory.create", "args": {"subject_type": "family_member", "subject_id": 7, "memory_type": "food_preference", "content": "Loves cucumbers."}}], "reply": "Got it."}
Note: when the subject is a known family member, use subject_type: "family_member" with that member's id.

Input: "remember that <family member name> has a shellfish allergy"  (CONTEXT.family_members has <family member name> id 7)
Output: {"tool_calls": [{"name": "memory.create", "args": {"subject_type": "family_member", "subject_id": 7, "memory_type": "restriction", "content": "Shellfish allergy.", "is_hard_restriction": true}}], "reply": "Got it."}
Note: safety-critical allergies and similar restrictions should be stored as hard restrictions.

Input: "what routines do we have saved for meal prep?"  (relevant routines are already present in household_memories)
Output: {"tool_calls": [], "reply": "You have a saved routine for meal prep on Sundays."}
Note: for pure questions about data already present in CONTEXT, answer directly instead of calling memory.search.

Input: "search memories for <family member name> allergies"  (CONTEXT.family_members has <family member name> id 7)
Output: {"tool_calls": [{"name": "memory.search", "args": {"query": "allerg", "subject_type": "family_member", "subject_id": 7, "memory_type": "restriction", "limit": 10}}], "reply": "Searching <family member name>'s restriction memories."}
Note: use memory.search when the user explicitly asks to search saved memories or filter memory records.
""",
}

# Full prompt with every example: what an input touching no known domain gets,
# and what the prompt-contract tests check.
SYSTEM_PROMPT = (
    BASE_PROMPT
    + "\nEXAMPLES (showing correct shape and when to ask vs act):\n"
    + "".join(EXAMPLES.values())
)


# Tools each domain may need. "meal" includes grocery so "add what's missing
# for <recipe>" works.
DOMAIN_TOOLS: dict[str, tuple[str, ...]] = {
    "grocery": ("grocery.add_items", "grocery.mark_purchased"),
    "meal": ("grocery.add_items", "grocery.mark_purchased", "meal_plan.create_entry"),
    "lunch": ("lunch_plan.create_entry",),
    "exercise": ("exercise.log_activity",),
    "memory": ("memory.create", "memory.search"),
}


@dataclass
class PromptContext:
    today: date
    domains: list[str]
    grocery_to_buy: list[dict]
    on_hand: list[dict]
    family_members: list[dict]
    planned_meals: list[dict]
    planned_lunches: list[dict]
    recipe_catalog: list[dict]
    recipe_matches: dict[str, list[dict]]
    household_memories: list[dict]


def _matches(text: str, words: tuple[str, ...]) -> bool:
    # Word-boundary match so "add" doesn't pull the grocery list for
    # "add a family member" and "list" doesn't pull it for "list memories".
    # The trailing `(?:e?s)?` also accepts simple plurals so natural phrasing
    # like "next week's dinners" / "lunches" still triggers the right context.
    pattern = r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:e?s)?\b"
    return re.search(pattern, text) is not None


# Token sets pruned of overly generic verbs ("add", "list", "plan") that fire
# across unrelated domains. The LLM is told to ask when context is missing, so
# a false negative is cheaper than a false positive that wastes prompt budget.
_GROCERY_TOKENS = (
    "grocery",
    "groceries",
    "shopping",
    "buy",
    "bought",
    "purchase",
    "purchased",
    "have",
    "kitchen",
    "fridge",
    "freezer",
    "pantry",
    "ingredient",
)
_MEAL_TOKENS = ("meal", "dinner", "breakfast", "snack", "cook", "eat")  # "lunch" handled below
_LUNCH_TOKENS = ("lunch", "school", "pack", "packed", "packing")
_EXERCISE_TOKENS = (
    "log",
    "logged",
    "exercise",
    "workout",
    "run",
    "ran",
    "walk",
    "walked",
    "lift",
    "set",
    "rep",
    "km",
    "mile",
    "minute",
    "gym",
    "hike",
    "cycling",
    "swim",
)
_MEMORY_TOKENS = (
    "remember",
    "memory",
    "memories",
    "forget",
    "allergy",
    "allergies",
    "allergic",
    "restriction",
    "prefer",
    "preference",
    "routine",
    "like",
    "love",
    "hate",
)


def _grocery_relevant(text: str) -> bool:
    return _matches(text.lower(), _GROCERY_TOKENS)


def _meal_relevant(text: str) -> bool:
    return _matches(text.lower(), _MEAL_TOKENS)


def _lunch_relevant(text: str) -> bool:
    return _matches(text.lower(), _LUNCH_TOKENS)


def _domains(text: str, *, meal: bool, lunch: bool) -> list[str]:
    """Domains an input touches, in EXAMPLES order; all of them when none match."""
    lowered = text.lower()
    found = {
        "grocery": _grocery_relevant(text),
        "meal": meal,
        "lunch": lunch,
        "exercise": _matches(lowered, _EXERCISE_TOKENS),
        "memory": _matches(lowered, _MEMORY_TOKENS),
    }
    return [d for d in EXAMPLES if found[d]] or list(EXAMPLES)


def build_context(db: DbSession, input_text: str, today: date | None = None) -> PromptContext:
    today = today or date.today()
    week_start = start_of_week(today)

    # Recipes load for meal/lunch input, or when a saved recipe is named ("add
    # the ingredients for chickpea curry"), so the assistant uses the household's
    # own ingredient lists instead of inventing them.
    recipes = list_recipes(db)
    lowered = input_text.lower()
    recipe_named = any(r.name.lower() in lowered for r in recipes)
    meal_or_lunch = _meal_relevant(input_text) or _lunch_relevant(input_text) or recipe_named

    # Groceries also load for meal/lunch-relevant input so the assistant can
    # suggest recipes that use what's already on hand ("what can I make for
    # dinner?", "pack a lunch from what we have").
    grocery_to_buy: list[dict] = []
    on_hand: list[dict] = []
    on_hand_rows = []
    if _grocery_relevant(input_text) or meal_or_lunch:
        grocery_to_buy = [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            for item in list_open_items(db)
        ]
        on_hand_rows = list_on_hand_items(db)
        on_hand = [
            {"id": item.id, "name": item.name, "location": item.location} for item in on_hand_rows
        ]

    family_members = [
        {"id": m.id, "name": m.name, "school_days": list(m.school_days)}
        for m in list_family_members(db)
    ]

    # Load the current AND upcoming week so "for next week's dinner, is the
    # grocery list enough?" works — shopping is planned a week ahead. Each entry
    # carries its date, so the LLM disambiguates which week against `today`.
    next_week_start = week_start + timedelta(days=7)

    planned_meals: list[dict] = []
    if _meal_relevant(input_text):
        planned_meals = [
            {
                "id": e.id,
                "date": e.date.isoformat(),
                "meal_type": e.meal_type,
                "title": e.title,
            }
            for e in list_meal_week_entries(db, week_start=week_start)
            + list_meal_week_entries(db, week_start=next_week_start)
        ]

    planned_lunches: list[dict] = []
    if _lunch_relevant(input_text):
        planned_lunches = [
            {
                "id": e.id,
                "family_member_id": e.family_member_id,
                "date": e.date.isoformat(),
                "items": e.items,
                "packed_status": e.packed_status,
            }
            for e in list_lunch_week_entries(db, week_start=week_start)
            + list_lunch_week_entries(db, week_start=next_week_start)
        ]

    # Recipe catalog (read-only) for meal/lunch planning: lets the assistant
    # suggest a dish/lunch from the household's saved recipes rather than
    # inventing one. Ingredients are names only — match against groceries above.
    recipe_catalog: list[dict] = []
    recipe_matches: dict[str, list[dict]] = {"ready": [], "almost": []}
    if meal_or_lunch:
        recipe_catalog = [
            {
                "id": r.id,
                "name": r.name,
                "meal_type": r.meal_type,
                "ingredients": list(r.ingredients),
                "notes": r.notes,
                "calories": r.calories,
                "protein_g": r.protein_g,
            }
            for r in recipes
        ]
        # Precomputed so the model doesn't have to cross-check ingredient lists.
        recipe_matches = match_recipes([r for r in recipes if r.meal_type != "lunch"], on_hand_rows)

    household_memories = [
        {
            "id": m.id,
            "subject_type": m.subject_type,
            "subject_id": m.subject_id,
            "memory_type": m.memory_type,
            "content": m.content,
            "is_hard_restriction": m.is_hard_restriction,
        }
        for m in list_memories(db, limit=50)
    ]

    return PromptContext(
        today=today,
        domains=_domains(
            input_text,
            meal=_meal_relevant(input_text) or recipe_named,
            lunch=_lunch_relevant(input_text),
        ),
        grocery_to_buy=grocery_to_buy,
        on_hand=on_hand,
        family_members=family_members,
        planned_meals=planned_meals,
        planned_lunches=planned_lunches,
        recipe_catalog=recipe_catalog,
        recipe_matches=recipe_matches,
        household_memories=household_memories,
    )


def render_messages(context: PromptContext, input_text: str) -> list[dict[str, str]]:
    context_block = {
        "today": context.today.isoformat(),
        "grocery_to_buy": context.grocery_to_buy,
        "on_hand": context.on_hand,
        "family_members": context.family_members,
        "planned_meals": context.planned_meals,
        "planned_lunches": context.planned_lunches,
        "recipe_catalog": context.recipe_catalog,
        "recipe_matches": context.recipe_matches,
        "household_memories": context.household_memories,
    }
    tool_names = {name for d in context.domains for name in DOMAIN_TOOLS[d]}
    system_content = (
        BASE_PROMPT
        + "\nEXAMPLES (showing correct shape and when to ask vs act):\n"
        + "".join(EXAMPLES[d] for d in context.domains)
        + "\nTOOL_CATALOG:\n"
        + json.dumps(tool_catalog(tool_names), separators=(",", ":"))
        + "\n\nCONTEXT:\n"
        + json.dumps(context_block, separators=(",", ":"), default=str)
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": input_text},
    ]
