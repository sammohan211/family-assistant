"""Recipe catalog service + assistant-context integration tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from family_assistant.ai_gateway.prompt import build_context
from family_assistant.meal_plan.services import (
    create_recipe,
    delete_recipe,
    get_recipe,
    get_recipe_by_name,
    list_meal_recipes,
    list_recipes,
    parse_ingredients,
    update_recipe,
)


def test_create_recipe_normalizes_and_persists(db_session: Session) -> None:
    recipe = create_recipe(
        db_session,
        name="  Butter Chicken & Rice  ",
        meal_type="dinner",
        ingredients=["Chicken Breast", "chicken breast", " Rice ", ""],
        notes="  weeknight  ",
        calories=650,
        protein_g=38,
    )
    assert recipe.name == "Butter Chicken & Rice"
    assert recipe.meal_type == "dinner"
    # de-duplicated, lowercased, blanks dropped, order preserved
    assert recipe.ingredients == ["chicken breast", "rice"]
    assert recipe.notes == "weeknight"
    assert recipe.calories == 650
    assert recipe.protein_g == 38


def test_create_recipe_rejects_unknown_meal_type(db_session: Session) -> None:
    with pytest.raises(ValueError, match="meal_type"):
        create_recipe(
            db_session,
            name="Brunch Thing",
            meal_type="brunch",
            ingredients=["eggs"],
        )


def test_get_recipe_by_name_is_case_insensitive(db_session: Session) -> None:
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    assert get_recipe_by_name(db_session, "egg tacos") is not None
    assert get_recipe_by_name(db_session, "  EGG TACOS ") is not None
    assert get_recipe_by_name(db_session, "nope") is None
    assert get_recipe_by_name(db_session, "   ") is None


def test_list_recipes_filters_by_meal_type(db_session: Session) -> None:
    create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    create_recipe(db_session, name="Buttered Toast", meal_type="lunch", ingredients=["bread"])

    lunches = list_recipes(db_session, meal_type="lunch")
    assert [r.name for r in lunches] == ["Apple", "Buttered Toast"]  # ordered by name
    assert len(list_recipes(db_session)) == 3


def test_delete_recipe(db_session: Session) -> None:
    recipe = create_recipe(db_session, name="Carrots", meal_type="lunch", ingredients=["carrots"])
    assert delete_recipe(db_session, recipe.id) is True
    assert delete_recipe(db_session, recipe.id) is False
    assert get_recipe_by_name(db_session, "Carrots") is None


def test_create_recipe_stores_instructions(db_session: Session) -> None:
    recipe = create_recipe(
        db_session,
        name="Egg Tacos",
        meal_type="dinner",
        ingredients=["eggs"],
        instructions="  Scramble eggs, warm tortillas, assemble.  ",
    )
    assert recipe.instructions == "Scramble eggs, warm tortillas, assemble."


def test_create_recipe_blank_instructions_is_none(db_session: Session) -> None:
    recipe = create_recipe(
        db_session, name="Plain", meal_type="dinner", ingredients=["x"], instructions="   "
    )
    assert recipe.instructions is None


def test_get_recipe_by_id(db_session: Session) -> None:
    recipe = create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    assert get_recipe(db_session, recipe.id) is recipe
    assert get_recipe(db_session, 999999) is None


def test_update_recipe_replaces_fields(db_session: Session) -> None:
    recipe = create_recipe(
        db_session, name="Tacos", meal_type="dinner", ingredients=["eggs"], calories=400
    )
    updated = update_recipe(
        db_session,
        recipe_id=recipe.id,
        name="Egg Tacos",
        meal_type="dinner",
        ingredients=["Eggs", "eggs", "Cheese"],
        instructions="Cook it.",
        notes="weeknight",
        calories=420,
        protein_g=22,
    )
    assert updated is not None
    assert updated.name == "Egg Tacos"
    assert updated.ingredients == ["eggs", "cheese"]
    assert updated.instructions == "Cook it."
    assert updated.notes == "weeknight"
    assert updated.calories == 420
    assert updated.protein_g == 22


def test_update_recipe_missing_returns_none(db_session: Session) -> None:
    assert (
        update_recipe(db_session, recipe_id=999999, name="X", meal_type="dinner", ingredients=[])
        is None
    )


def test_list_meal_recipes_excludes_lunch(db_session: Session) -> None:
    create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    create_recipe(db_session, name="Oatmeal", meal_type="breakfast", ingredients=["oats"])

    names = [r.name for r in list_meal_recipes(db_session)]
    assert names == ["Egg Tacos", "Oatmeal"]  # ordered by name, no lunch components


def test_parse_ingredients_splits_and_normalizes() -> None:
    assert parse_ingredients("Eggs\n cheese \n\nEGGS\n") == ["eggs", "cheese"]
    assert parse_ingredients("   ") == []


def test_build_context_includes_recipes_for_meal_input(db_session: Session) -> None:
    create_recipe(
        db_session,
        name="Butter Chicken & Rice",
        meal_type="dinner",
        ingredients=["chicken breast", "rice"],
        calories=650,
        protein_g=38,
    )
    ctx = build_context(db_session, "what can I make for dinner?", today=date(2026, 5, 31))
    names = [r["name"] for r in ctx.recipe_catalog]
    assert "Butter Chicken & Rice" in names
    entry = next(r for r in ctx.recipe_catalog if r["name"] == "Butter Chicken & Rice")
    assert entry["ingredients"] == ["chicken breast", "rice"]
    assert entry["calories"] == 650


def test_build_context_includes_recipes_for_lunch_input(db_session: Session) -> None:
    create_recipe(db_session, name="Grilled Cheese", meal_type="lunch", ingredients=["bread"])
    ctx = build_context(db_session, "pack a lunch for tomorrow", today=date(2026, 5, 31))
    assert any(r["name"] == "Grilled Cheese" for r in ctx.recipe_catalog)


def test_build_context_omits_recipes_for_unrelated_input(db_session: Session) -> None:
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    ctx = build_context(db_session, "add milk to the grocery list", today=date(2026, 5, 31))
    assert ctx.recipe_catalog == []


def test_build_context_includes_next_weeks_meals(db_session: Session) -> None:
    from family_assistant.auth.models import User
    from family_assistant.meal_plan.models import MealPlanEntry

    user = User(name="Planner", email="planner@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()

    today = date(2026, 6, 1)  # Monday; current week 1-7, next week 8-14
    db_session.add_all(
        [
            MealPlanEntry(
                date=date(2026, 6, 3),
                meal_type="dinner",
                title="This Week Tacos",
                created_by_user_id=user.id,
            ),
            MealPlanEntry(
                date=date(2026, 6, 10),
                meal_type="dinner",
                title="Next Week Curry",
                created_by_user_id=user.id,
            ),
        ]
    )
    db_session.commit()

    ctx = build_context(
        db_session, "for next week's dinner, is the grocery list enough?", today=today
    )
    titles = {m["title"] for m in ctx.planned_meals}
    # Both the current and the upcoming week are now in context.
    assert {"This Week Tacos", "Next Week Curry"} <= titles
