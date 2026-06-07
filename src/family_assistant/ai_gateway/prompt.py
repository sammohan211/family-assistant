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
from family_assistant.grocery.services import list_open_items
from family_assistant.lunch_plan.services import (
    list_family_members,
    start_of_week,
)
from family_assistant.lunch_plan.services import (
    list_week_entries as list_lunch_week_entries,
)
from family_assistant.meal_plan.services import list_recipes
from family_assistant.meal_plan.services import list_week_entries as list_meal_week_entries
from family_assistant.memory.services import list_memories

SYSTEM_PROMPT = """You are a household assistant for a single household with two adult users.
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
- Keep reply short — one or two sentences.

EXAMPLES (showing correct shape and when to ask vs act):

Input: "add milk and bread to the list"
Output: {"tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "milk"}, {"name": "bread"}]}}], "reply": "Added milk and bread."}
Note: items is a list of OBJECTS, each with a name. Don't flatten to a string.
      Don't ask for quantity/unit/category — they're optional.

Input: "mark eggs as purchased"  (CONTEXT.open_grocery_items has Eggs id 41)
Output: {"tool_calls": [{"name": "grocery.mark_purchased", "args": {"item_ids": [41]}}], "reply": "Marked eggs as purchased."}
Note: use the integer id from CONTEXT.open_grocery_items; do not pass item names to the tool.

Input: "I bought the milk"  (CONTEXT.open_grocery_items has 2% milk id 12 and whole milk id 15)
Output: {"tool_calls": [], "reply": "I see two milk items — 2% (id 12) and whole (id 15). Which one did you buy?"}
Note: if multiple existing items match, ask instead of guessing.

Input: "mark eggs and milk as purchased"  (CONTEXT.open_grocery_items has Eggs id 41 and Milk id 52)
Output: {"tool_calls": [{"name": "grocery.mark_purchased", "args": {"item_ids": [41, 52]}}], "reply": "Marked eggs and milk as purchased."}
Note: when multiple existing grocery items are named unambiguously, pass all matching ids in one item_ids list.

Input: "schedule dinner for Saturday"
Output: {"tool_calls": [], "reply": "What should we have for dinner Saturday?"}
Note: meal_plan.create_entry requires a title — don't guess one.

Input: "plan tacos for Friday"
Output: {"tool_calls": [{"name": "meal_plan.create_entry", "args": {"date": "2026-05-22", "meal_type": "dinner", "title": "Tacos"}}], "reply": "Planned tacos for Friday dinner."}
Note: infer meal_type from the meal named in the request when it is explicit.

Input: "what can I make for dinner with what we have?"  (CONTEXT.recipe_catalog has dinner recipes; CONTEXT.open_grocery_items lists what's on hand)
Output: {"tool_calls": [], "reply": "From your recipes, Butter Chicken & Rice fits — you've got chicken and rice on the list. Want me to plan it?"}
Note: suggest from recipe_catalog, preferring recipes whose ingredients already appear in open_grocery_items. Do NOT invent recipes that aren't in the catalog; if nothing matches, say so and offer to plan something anyway.

Input: "for next week's dinners, is the grocery list enough or do we need more?"  (CONTEXT.planned_meals lists this week's and next week's dinners by title and date; CONTEXT.recipe_catalog has their ingredients; CONTEXT.open_grocery_items is what's on hand)
Output: {"tool_calls": [], "reply": "Next week you've planned Butter Chicken & Rice and Egg Tacos. You already have rice and eggs, but you're missing chicken breast, butter chicken sauce, tortillas, and cheese. Want me to add those to the grocery list?"}
Note: match each planned meal title to a recipe in recipe_catalog, compare that recipe's ingredients against open_grocery_items, and report what's missing. planned_meals and planned_lunches cover the current AND upcoming week — use each entry's date to focus on the week the user asked about. Offer to add the missing items rather than adding them unprompted.

Input: "plan butter chicken for Friday"  (CONTEXT.recipe_catalog has "Butter Chicken & Rice")
Output: {"tool_calls": [{"name": "meal_plan.create_entry", "args": {"date": "2026-05-22", "meal_type": "dinner", "title": "Butter Chicken & Rice"}}], "reply": "Planned Butter Chicken & Rice for Friday dinner."}
Note: when the request names a recipe that exists in recipe_catalog, use that recipe's exact name as the meal title.

Input: "pack a lunch for <family member name> tomorrow"  (CONTEXT.family_members has <family member name> id 7; CONTEXT.recipe_catalog has lunch components grouped by note: Carb/Fruit/Veg/Treat)
Output: {"tool_calls": [{"name": "lunch_plan.create_entry", "args": {"family_member_id": 7, "date": "2026-05-21", "items": [{"name": "Grilled Cheese"}, {"name": "Apple"}, {"name": "Cookies"}]}}], "reply": "Packed grilled cheese, an apple, and a cookie for <family member name>."}
Note: compose a school lunch from recipe_catalog lunch components — typically one Carb plus a Fruit and a Treat. Respect any hard restriction in household_memories.

Input: "pack <family member name> a turkey sandwich and apple slices tomorrow"  (CONTEXT.family_members has <family member name> id 7)
Output: {"tool_calls": [{"name": "lunch_plan.create_entry", "args": {"family_member_id": 7, "date": "2026-05-21", "items": [{"name": "turkey sandwich"}, {"name": "apple slices"}]}}], "reply": "Planned <family member name>'s lunch for tomorrow."}
Note: items must be a list of objects; resolve the spoken family-member name to family_member_id from context.

Input: "pack lunch for tomorrow"  (CONTEXT.family_members has multiple family members)
Output: {"tool_calls": [], "reply": "Which family member is this lunch for?"}
Note: if a required field is missing and cannot be inferred safely, ask a clarifying question.

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

Input: "pack peanut butter for <family member name> tomorrow"  (household_memories has <family member name>: peanut hard restriction)
Output: {"tool_calls": [], "reply": "Memory says <family member name> has a peanut restriction. Want me to pick something else?"}
Note: when a request conflicts with a hard restriction in household_memories, ask instead of acting.

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
"""


@dataclass
class PromptContext:
    today: date
    open_grocery_items: list[dict]
    family_members: list[dict]
    planned_meals: list[dict]
    planned_lunches: list[dict]
    recipe_catalog: list[dict]
    household_memories: list[dict]


def _matches(text: str, words: tuple[str, ...]) -> bool:
    # Word-boundary match so "add" doesn't pull the grocery list for
    # "add a family member" and "list" doesn't pull it for "list memories".
    return re.search(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", text) is not None


# Token sets pruned of overly generic verbs ("add", "list", "plan") that fire
# across unrelated domains. The LLM is told to ask when context is missing, so
# a false negative is cheaper than a false positive that wastes prompt budget.
_GROCERY_TOKENS = ("grocery", "groceries", "shopping", "buy", "bought", "purchase", "purchased")
_MEAL_TOKENS = ("meal", "dinner", "breakfast", "snack", "cook", "eat")  # "lunch" handled below
_LUNCH_TOKENS = ("lunch", "school", "pack", "packed", "packing")


def _grocery_relevant(text: str) -> bool:
    return _matches(text.lower(), _GROCERY_TOKENS)


def _meal_relevant(text: str) -> bool:
    return _matches(text.lower(), _MEAL_TOKENS)


def _lunch_relevant(text: str) -> bool:
    return _matches(text.lower(), _LUNCH_TOKENS)


def build_context(db: DbSession, input_text: str, today: date | None = None) -> PromptContext:
    today = today or date.today()
    week_start = start_of_week(today)

    # Groceries also load for meal/lunch-relevant input so the assistant can
    # suggest recipes that use what's already on hand ("what can I make for
    # dinner?", "pack a lunch from what we have").
    open_grocery_items: list[dict] = []
    if _grocery_relevant(input_text) or _meal_relevant(input_text) or _lunch_relevant(input_text):
        open_grocery_items = [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            for item in list_open_items(db)
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
    if _meal_relevant(input_text) or _lunch_relevant(input_text):
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
            for r in list_recipes(db)
        ]

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
        open_grocery_items=open_grocery_items,
        family_members=family_members,
        planned_meals=planned_meals,
        planned_lunches=planned_lunches,
        recipe_catalog=recipe_catalog,
        household_memories=household_memories,
    )


def render_messages(context: PromptContext, input_text: str) -> list[dict[str, str]]:
    context_block = {
        "today": context.today.isoformat(),
        "open_grocery_items": context.open_grocery_items,
        "family_members": context.family_members,
        "planned_meals": context.planned_meals,
        "planned_lunches": context.planned_lunches,
        "recipe_catalog": context.recipe_catalog,
        "household_memories": context.household_memories,
    }
    system_content = (
        SYSTEM_PROMPT
        + "\n\nTOOL_CATALOG:\n"
        + json.dumps(tool_catalog(), indent=2)
        + "\n\nCONTEXT:\n"
        + json.dumps(context_block, indent=2, default=str)
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": input_text},
    ]
