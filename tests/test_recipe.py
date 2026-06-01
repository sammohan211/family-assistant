"""Recipe catalog service + assistant-context integration tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from family_assistant.ai_gateway.prompt import build_context
from family_assistant.meal_plan.services import (
    create_recipe,
    delete_recipe,
    get_recipe_by_name,
    list_recipes,
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
