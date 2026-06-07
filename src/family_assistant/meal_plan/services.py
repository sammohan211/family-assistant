"""Meal planning CRUD services (PRD Section 10.5)."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.meal_plan.models import MealPlanEntry, Recipe

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


# ---------------------------------------------------------------------------
# Recipe catalog (household-shared)
# ---------------------------------------------------------------------------


def _normalize_ingredients(ingredients: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in ingredients:
        cleaned = raw.strip().lower()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def parse_ingredients(raw: str) -> list[str]:
    """Split a free-text ingredients block (one per line) into a normalized list."""
    return _normalize_ingredients(raw.splitlines())


def list_recipes(db: DbSession, *, meal_type: str | None = None) -> list[Recipe]:
    statement = select(Recipe)
    if meal_type is not None:
        statement = statement.where(Recipe.meal_type == meal_type)
    return list(db.scalars(statement.order_by(Recipe.name.asc())).all())


def list_meal_recipes(db: DbSession) -> list[Recipe]:
    """Catalog recipes that are NOT school-lunch components (the meal catalog)."""
    statement = select(Recipe).where(Recipe.meal_type != "lunch").order_by(Recipe.name.asc())
    return list(db.scalars(statement).all())


def get_recipe(db: DbSession, recipe_id: int) -> Recipe | None:
    return db.get(Recipe, recipe_id)


def get_recipe_by_name(db: DbSession, name: str) -> Recipe | None:
    cleaned = name.strip()
    if not cleaned:
        return None
    return db.scalars(select(Recipe).where(Recipe.name.ilike(cleaned))).first()


def create_recipe(
    db: DbSession,
    *,
    name: str,
    meal_type: str,
    ingredients: list[str],
    instructions: str | None = None,
    notes: str | None = None,
    calories: int | None = None,
    protein_g: int | None = None,
) -> Recipe:
    if meal_type not in MEAL_TYPES:
        raise ValueError(f"Unknown meal_type: {meal_type!r}")
    recipe = Recipe(
        name=name.strip(),
        meal_type=meal_type,
        ingredients=_normalize_ingredients(ingredients),
        instructions=instructions.strip() if instructions else None,
        notes=notes.strip() if notes else None,
        calories=calories,
        protein_g=protein_g,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe(
    db: DbSession,
    *,
    recipe_id: int,
    name: str,
    meal_type: str,
    ingredients: list[str],
    instructions: str | None = None,
    notes: str | None = None,
    calories: int | None = None,
    protein_g: int | None = None,
) -> Recipe | None:
    if meal_type not in MEAL_TYPES:
        raise ValueError(f"Unknown meal_type: {meal_type!r}")
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        return None
    recipe.name = name.strip()
    recipe.meal_type = meal_type
    recipe.ingredients = _normalize_ingredients(ingredients)
    recipe.instructions = instructions.strip() if instructions else None
    recipe.notes = notes.strip() if notes else None
    recipe.calories = calories
    recipe.protein_g = protein_g
    db.commit()
    db.refresh(recipe)
    return recipe


def delete_recipe(db: DbSession, recipe_id: int) -> bool:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None:
        return False
    db.delete(recipe)
    db.commit()
    return True


def start_of_week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _with_user(statement):
    return statement.options(selectinload(MealPlanEntry.created_by_user))


def list_week_entries(db: DbSession, *, week_start: date) -> list[MealPlanEntry]:
    week_end = week_start + timedelta(days=6)
    statement = (
        select(MealPlanEntry)
        .where(MealPlanEntry.date >= week_start, MealPlanEntry.date <= week_end)
        .order_by(MealPlanEntry.date, MealPlanEntry.meal_type, MealPlanEntry.id)
    )
    return list(db.scalars(_with_user(statement)).all())


def list_entries_for_date(db: DbSession, *, day: date) -> list[MealPlanEntry]:
    statement = (
        select(MealPlanEntry)
        .where(MealPlanEntry.date == day)
        .order_by(MealPlanEntry.meal_type, MealPlanEntry.id)
    )
    return list(db.scalars(_with_user(statement)).all())


def list_recent_entries(
    db: DbSession, limit: int = 12, favorites_only: bool = False
) -> list[MealPlanEntry]:
    statement = select(MealPlanEntry)
    if favorites_only:
        statement = statement.where(MealPlanEntry.is_favorite.is_(True))
    statement = statement.order_by(MealPlanEntry.updated_at.desc(), MealPlanEntry.id.desc()).limit(
        limit
    )
    return list(db.scalars(_with_user(statement)).all())


def get_meal_plan_entry(db: DbSession, entry_id: int) -> MealPlanEntry | None:
    return db.get(MealPlanEntry, entry_id)


def create_meal_plan_entry(
    db: DbSession,
    *,
    user: User,
    entry_date: date,
    meal_type: str,
    title: str,
    notes: str | None,
    is_favorite: bool,
) -> MealPlanEntry:
    entry = MealPlanEntry(
        date=entry_date,
        meal_type=meal_type,
        title=title.strip(),
        notes=notes.strip() if notes else None,
        is_favorite=is_favorite,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_meal_plan_entry(
    db: DbSession,
    *,
    entry_id: int,
    entry_date: date,
    meal_type: str,
    title: str,
    notes: str | None,
    is_favorite: bool,
) -> MealPlanEntry | None:
    entry = db.get(MealPlanEntry, entry_id)
    if entry is None:
        return None
    entry.date = entry_date
    entry.meal_type = meal_type
    entry.title = title.strip()
    entry.notes = notes.strip() if notes else None
    entry.is_favorite = is_favorite
    db.commit()
    db.refresh(entry)
    return entry


def delete_meal_plan_entry(db: DbSession, entry_id: int) -> bool:
    entry = db.get(MealPlanEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True


def duplicate_meal_plan_entry(
    db: DbSession,
    *,
    entry_id: int,
    user: User,
    entry_date: date,
) -> MealPlanEntry | None:
    entry = db.get(MealPlanEntry, entry_id)
    if entry is None:
        return None
    return create_meal_plan_entry(
        db,
        user=user,
        entry_date=entry_date,
        meal_type=entry.meal_type,
        title=entry.title,
        notes=entry.notes,
        is_favorite=entry.is_favorite,
    )
