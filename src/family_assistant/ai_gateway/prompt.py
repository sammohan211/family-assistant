# ruff: noqa: E501  — system prompt examples must stay on one line per JSON output.
"""Prompt construction for the AI Gateway.

Command-aware: the system prompt is fixed, but the context block is built by
pre-fetching relevant DB state per domain heuristic on the input text. Keeps
the LLM able to answer "do I have apples?" without needing a separate read
tool round-trip.
"""

import json
from dataclasses import dataclass
from datetime import date

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

Input: "add milk, cream, beer, wine and cheese"
Output: {"tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "milk"}, {"name": "cream"}, {"name": "beer"}, {"name": "wine"}, {"name": "cheese"}]}}], "reply": "Added five items."}

Input: "remove the milk"  (CONTEXT.open_grocery_items has 2% milk and whole milk)
Output: {"tool_calls": [], "reply": "I see two milks — 2% (id 12) and whole (id 15). Which one?"}

Input: "schedule dinner for Saturday"
Output: {"tool_calls": [], "reply": "What should we have for dinner Saturday?"}
Note: meal_plan.create_entry requires a title — don't guess one.

Input: "log a 30 minute run for 2026-05-20"
Output: {"tool_calls": [{"name": "exercise.log_activity", "args": {"exercise_name": "run", "date": "2026-05-20", "duration_minutes": 30}}], "reply": "Logged a 30-minute run."}

Input: "log a workout today"
Output: {"tool_calls": [], "reply": "Which exercise — a run, a lift, something specific?"}

Input: "pack peanut butter for Maya tomorrow"  (household_memories has Maya: peanut hard restriction)
Output: {"tool_calls": [], "reply": "Memory says Maya has a peanut restriction. Want me to pick something else?"}

Input: "remember that we always do meal prep on Sundays"
Output: {"tool_calls": [{"name": "memory.create", "args": {"subject_type": "household", "memory_type": "routine", "content": "We always do meal prep on Sundays."}}], "reply": "Got it."}
"""


@dataclass
class PromptContext:
    today: date
    open_grocery_items: list[dict]
    family_members: list[dict]
    this_weeks_meals: list[dict]
    this_weeks_lunches: list[dict]
    household_memories: list[dict]


def _grocery_relevant(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ("grocery", "shopping", "buy", "purchase", "add", "list"))


def _meal_relevant(text: str) -> bool:
    t = text.lower()
    return any(
        w in t for w in ("meal", "dinner", "breakfast", "lunch", "snack", "cook", "eat", "plan")
    )


def _lunch_relevant(text: str) -> bool:
    t = text.lower()
    return "lunch" in t or "school" in t or "pack" in t


def build_context(db: DbSession, input_text: str, today: date | None = None) -> PromptContext:
    today = today or date.today()
    week_start = start_of_week(today)

    open_grocery_items: list[dict] = []
    if _grocery_relevant(input_text):
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

    this_weeks_meals: list[dict] = []
    if _meal_relevant(input_text):
        this_weeks_meals = [
            {
                "id": e.id,
                "date": e.date.isoformat(),
                "meal_type": e.meal_type,
                "title": e.title,
            }
            for e in list_meal_week_entries(db, week_start=week_start)
        ]

    this_weeks_lunches: list[dict] = []
    if _lunch_relevant(input_text):
        this_weeks_lunches = [
            {
                "id": e.id,
                "family_member_id": e.family_member_id,
                "date": e.date.isoformat(),
                "items": e.items,
                "packed_status": e.packed_status,
            }
            for e in list_lunch_week_entries(db, week_start=week_start)
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
        this_weeks_meals=this_weeks_meals,
        this_weeks_lunches=this_weeks_lunches,
        household_memories=household_memories,
    )


def render_messages(context: PromptContext, input_text: str) -> list[dict[str, str]]:
    context_block = {
        "today": context.today.isoformat(),
        "open_grocery_items": context.open_grocery_items,
        "family_members": context.family_members,
        "this_weeks_meals": context.this_weeks_meals,
        "this_weeks_lunches": context.this_weeks_lunches,
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
