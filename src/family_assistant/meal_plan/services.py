"""Meal planning CRUD services (PRD Section 10.5)."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.meal_plan.models import MealPlanEntry

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")


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
