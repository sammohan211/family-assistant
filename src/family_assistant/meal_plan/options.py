""" "What can I make?" — recipes matched against groceries on hand.

Code does the matching (the part small models get wrong); the LLM only picks a
few of the matches and says why, mirroring the exercise priorities card.

Matching is by ingredient name, deliberately simple and explainable:
- names are lower-cased, split into words, and naively singularised;
- an ingredient is on hand when an on-hand item contains all its words
  ("cheese" ← "Cheddar Cheese", "chicken" ← "Chicken breast"; but not
  "chicken breast" ← "Chicken", which would also match "chicken nuggets");
- a recipe with no ingredients is on hand when an item has the recipe's name.
"""

import json
import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.grocery.models import GroceryItem
from family_assistant.grocery.services import list_on_hand_items
from family_assistant.meal_plan.models import MealPlanEntry, Recipe
from family_assistant.memory.services import list_memories

MAX_MISSING = 2
MAX_PICKS = 3
RECENT_DAYS = 7


def _words(name: str) -> list[str]:
    words = []
    for word in re.findall(r"[a-z0-9]+", name.lower()):
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("oes"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.append(word)
    return words


def _covers(item: list[str], wanted: list[str]) -> bool:
    """True when the on-hand ``item`` words satisfy the ``wanted`` name."""
    return bool(wanted) and set(wanted) <= set(item)


def _find(wanted: str, on_hand: list[GroceryItem]) -> GroceryItem | None:
    words = _words(wanted)
    return next((item for item in on_hand if _covers(_words(item.name), words)), None)


def match_recipes(recipes: list[Recipe], on_hand: list[GroceryItem]) -> dict[str, list[dict]]:
    """Split recipes into ``ready`` (all on hand) and ``almost`` (1-2 missing)."""
    ready: list[dict] = []
    almost: list[dict] = []
    for recipe in recipes:
        if not recipe.ingredients:
            item = _find(recipe.name, on_hand)
            if item is not None:
                ready.append(_entry(recipe, have=[item], missing=[]))
            continue
        have: list[GroceryItem] = []
        missing: list[str] = []
        for ingredient in recipe.ingredients:
            item = _find(ingredient, on_hand)
            if item is None:
                missing.append(ingredient)
            elif item not in have:
                have.append(item)
        if not missing:
            ready.append(_entry(recipe, have=have, missing=[]))
        elif have and len(missing) <= MAX_MISSING:
            almost.append(_entry(recipe, have=have, missing=missing))
    almost.sort(key=lambda r: (len(r["missing"]), r["name"]))
    return {"ready": ready, "almost": almost}


def _entry(recipe: Recipe, *, have: list[GroceryItem], missing: list[str]) -> dict:
    return {
        "name": recipe.name,
        "meal_type": recipe.meal_type,
        "have": [item.name for item in have],
        "from_freezer": [item.name for item in have if item.location == "freezer"],
        "missing": missing,
    }


def recent_meal_titles(db: DbSession, *, today: date) -> list[str]:
    statement = (
        select(MealPlanEntry.title)
        .where(MealPlanEntry.date >= today - timedelta(days=RECENT_DAYS))
        .where(MealPlanEntry.date <= today)
        .order_by(MealPlanEntry.date.desc())
    )
    return list(dict.fromkeys(db.scalars(statement).all()))


def build_options(db: DbSession, recipes: list[Recipe]) -> dict[str, Any]:
    on_hand = list_on_hand_items(db)
    return {"on_hand_count": len(on_hand), **match_recipes(recipes, on_hand)}


# ---------------------------------------------------------------------------
# LLM pick
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You help a family decide what to cook. You receive JSON with recipes that code
has already checked against the groceries they have on hand:
- "ready": everything is on hand ("from_freezer" items need thawing);
- "almost": one or two ingredients are "missing".
Also "recent_meals" (eaten in the last week) and "food_notes" (preferences and
restrictions; never pick anything that breaks a restriction).

Pick up to 3 recipes, preferring "ready" ones and ones not in recent_meals.
Copy each name exactly from the lists. For each, write one short, friendly
sentence saying why; for an "almost" recipe, name what's missing. Do not
invent recipes or ingredients.

Reply with JSON only:
{"picks": [{"name": "<recipe name>", "reason": "<one sentence>"}]}
"""


def build_messages(
    options: dict[str, Any], recent_meals: list[str], food_notes: list[str], today: date
) -> list[dict[str, str]]:
    payload = {
        "today": today.isoformat(),
        "ready": [
            {"name": r["name"], "have": r["have"], "from_freezer": r["from_freezer"]}
            for r in options["ready"]
        ],
        "almost": [
            {"name": r["name"], "have": r["have"], "missing": r["missing"]}
            for r in options["almost"]
        ],
        "recent_meals": recent_meals,
        "food_notes": food_notes,
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


class _Pick(BaseModel):
    name: str
    reason: str = ""


class _Answer(BaseModel):
    picks: list[_Pick]


def validate_picks(raw: Any, options: dict[str, Any]) -> list[dict[str, str]]:
    """Keep picks that name a matched recipe (ignoring case), at most MAX_PICKS."""
    try:
        answer = _Answer.model_validate(raw)
    except ValueError:
        return []
    names = {r["name"].lower(): r["name"] for r in options["ready"] + options["almost"]}
    picks: list[dict[str, str]] = []
    for pick in answer.picks:
        name = names.get(pick.name.strip().lower())
        if name and name not in {p["name"] for p in picks}:
            picks.append({"name": name, "reason": pick.reason.strip()})
    return picks[:MAX_PICKS]


def food_notes(db: DbSession) -> list[str]:
    return [
        m.content
        for m in list_memories(db, limit=50)
        if m.is_hard_restriction or m.memory_type in ("food_preference", "restriction")
    ]


def suggest(db: DbSession, llm: Any, options: dict[str, Any], today: date) -> list[dict] | None:
    """Ask the LLM to pick; ``None`` when the call fails or returns nothing usable."""
    if not options["ready"] and not options["almost"]:
        return []
    messages = build_messages(options, recent_meal_titles(db, today=today), food_notes(db), today)
    try:
        raw = llm.chat_json(messages)
    except Exception:  # httpx errors, JSON decode: show the matches without picks
        return None
    return validate_picks(raw, options) or None


class CannedMealOptionsLLM:
    """Offline stand-in (USE_MOCK_LLM=true): picks the first candidates."""

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = json.loads(messages[-1]["content"])
        candidates = payload["ready"] + payload["almost"]
        return {
            "picks": [
                {"name": c["name"], "reason": "Offline mode — no model was consulted."}
                for c in candidates[:MAX_PICKS]
            ]
        }
