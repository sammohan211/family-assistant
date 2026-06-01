"""Seed the household recipe catalog with a starter set.

One-off, idempotent import: creates a spread of everyday household recipes in
the shared ``recipes`` table via the service layer (so validation + ingredient
normalization apply). Existing recipes (matched case-insensitively by name) are
skipped, so re-running is safe.

Macros are deliberately rough — a planning aid, not a tracking ledger. Edit any
of these in the app later; this is just a usable starting point so meal planning
has something to draw from against what's on the grocery list.

Run inside the app container:

    docker compose exec -T app python - < scripts/seed_recipes.py
"""

from __future__ import annotations

from family_assistant.db import get_sessionmaker
from family_assistant.meal_plan.services import create_recipe, get_recipe_by_name

# (name, meal_type, ingredients, notes, calories, protein_g)
#
# Curated with the household to match what's actually cooked/packed:
#   - Dinners: the real 6-meal rotation.
#   - School lunches: stored as individual *components* (carb / fruit / veg /
#     treat) so the assistant can mix-and-match them into a packed lunch
#     (typically a carb + some fruit + a treat). The note records the group.
RECIPES: list[tuple[str, str, list[str], str | None, int | None, int | None]] = [
    # --- Dinner (the household's real rotation) ---
    (
        "Roasted Marinated Chicken with Salad",
        "dinner",
        ["chicken breast", "marinade", "packaged salad"],
        None,
        500,
        45,
    ),
    ("Egg Tacos", "dinner", ["corn tortillas", "eggs", "cheese", "salsa"], None, 400, 20),
    (
        "Rice & Lentil Curry",
        "dinner",
        ["rice", "lentils", "onion", "curry spices"],
        "Vegetarian.",
        480,
        16,
    ),
    (
        "Sheet Pan Salmon with Zucchini or Potato",
        "dinner",
        ["salmon", "zucchini", "potato", "olive oil"],
        None,
        550,
        40,
    ),
    (
        "Butter Chicken & Rice",
        "dinner",
        ["chicken breast", "butter chicken sauce", "rice"],
        None,
        650,
        38,
    ),
    (
        "Chicken Nuggets",
        "dinner",
        ["chicken nuggets", "fries"],
        "Kid meal.",
        450,
        20,
    ),
    # --- School lunch components (carb) ---
    ("Buttered Toast", "lunch", ["bread", "butter"], "Carb.", 200, 5),
    ("Grilled Cheese", "lunch", ["bread", "cheese", "butter"], "Carb.", 350, 12),
    ("Naan Bites", "lunch", ["naan"], "Carb.", 250, 7),
    # --- School lunch components (fruit) ---
    ("Apple", "lunch", ["apple"], "Fruit.", 95, 0),
    ("Strawberries", "lunch", ["strawberries"], "Fruit.", 50, 1),
    # --- School lunch components (veg) ---
    ("Carrots", "lunch", ["carrots"], "Veg.", 50, 1),
    # --- School lunch components (treat) ---
    ("Cookies", "lunch", ["cookies"], "Treat.", 160, 2),
    ("Bag of Chips", "lunch", ["chips"], "Treat.", 150, 2),
]


def main() -> None:
    created = 0
    skipped = 0
    with get_sessionmaker()() as db:
        for name, meal_type, ingredients, notes, calories, protein_g in RECIPES:
            if get_recipe_by_name(db, name) is not None:
                print(f"skip   {name} (already exists)")
                skipped += 1
                continue
            create_recipe(
                db,
                name=name,
                meal_type=meal_type,
                ingredients=ingredients,
                notes=notes,
                calories=calories,
                protein_g=protein_g,
            )
            print(f"create {name}")
            created += 1
    print(f"\nDone: {created} created, {skipped} skipped, {len(RECIPES)} total.")


if __name__ == "__main__":
    main()
