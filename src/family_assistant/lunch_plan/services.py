"""School lunch planning CRUD services (PRD Section 10.6)."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.family_member.models import FamilyMember
from family_assistant.lunch_plan.models import LunchPlanEntry

PACKED_STATUSES = ("planned", "packed")


def start_of_week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _with_relations(statement):
    return statement.options(
        selectinload(LunchPlanEntry.family_member),
        selectinload(LunchPlanEntry.created_by_user),
    )


def list_family_members(db: DbSession) -> list[FamilyMember]:
    statement = select(FamilyMember).order_by(FamilyMember.name)
    return list(db.scalars(statement).all())


def list_week_entries(db: DbSession, *, week_start: date) -> list[LunchPlanEntry]:
    week_end = week_start + timedelta(days=6)
    statement = (
        select(LunchPlanEntry)
        .where(LunchPlanEntry.date >= week_start, LunchPlanEntry.date <= week_end)
        .order_by(LunchPlanEntry.date, LunchPlanEntry.family_member_id, LunchPlanEntry.id)
    )
    return list(db.scalars(_with_relations(statement)).all())


def get_lunch_plan_entry(db: DbSession, entry_id: int) -> LunchPlanEntry | None:
    return db.get(LunchPlanEntry, entry_id)


def create_lunch_plan_entry(
    db: DbSession,
    *,
    user: User,
    family_member_id: int,
    entry_date: date,
    items: list[dict[str, str]],
    notes: str | None,
    packed_status: str,
) -> LunchPlanEntry:
    entry = LunchPlanEntry(
        family_member_id=family_member_id,
        date=entry_date,
        items=items,
        notes=notes.strip() if notes else None,
        packed_status=packed_status,
        created_by_user_id=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_lunch_plan_entry(
    db: DbSession,
    *,
    entry_id: int,
    family_member_id: int,
    entry_date: date,
    items: list[dict[str, str]],
    notes: str | None,
    packed_status: str,
) -> LunchPlanEntry | None:
    entry = db.get(LunchPlanEntry, entry_id)
    if entry is None:
        return None
    entry.family_member_id = family_member_id
    entry.date = entry_date
    entry.items = items
    entry.notes = notes.strip() if notes else None
    entry.packed_status = packed_status
    db.commit()
    db.refresh(entry)
    return entry


def delete_lunch_plan_entry(db: DbSession, entry_id: int) -> bool:
    entry = db.get(LunchPlanEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True


def set_packed_status(db: DbSession, *, entry_id: int, packed_status: str) -> LunchPlanEntry | None:
    entry = db.get(LunchPlanEntry, entry_id)
    if entry is None:
        return None
    entry.packed_status = packed_status
    db.commit()
    db.refresh(entry)
    return entry
