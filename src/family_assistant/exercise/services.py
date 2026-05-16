"""Exercise CRUD services (PRD Section 10.7)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.exercise.models import ExerciseEntry


def _with_user(statement):
    return statement.options(selectinload(ExerciseEntry.user))


def list_exercise_entries(db: DbSession, limit: int = 50) -> list[ExerciseEntry]:
    statement = (
        select(ExerciseEntry)
        .order_by(
            ExerciseEntry.date.desc(),
            ExerciseEntry.created_at.desc(),
            ExerciseEntry.id.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(_with_user(statement)).all())


def get_exercise_entry(db: DbSession, entry_id: int) -> ExerciseEntry | None:
    return db.get(ExerciseEntry, entry_id)


def create_exercise_entry(
    db: DbSession,
    *,
    user: User,
    activity_type: str,
    duration_minutes: int,
    entry_date: date,
    notes: str | None,
) -> ExerciseEntry:
    entry = ExerciseEntry(
        user_id=user.id,
        activity_type=activity_type.strip(),
        duration_minutes=duration_minutes,
        date=entry_date,
        notes=notes.strip() if notes else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_exercise_entry(
    db: DbSession,
    *,
    entry_id: int,
    activity_type: str,
    duration_minutes: int,
    entry_date: date,
    notes: str | None,
) -> ExerciseEntry | None:
    entry = db.get(ExerciseEntry, entry_id)
    if entry is None:
        return None
    entry.activity_type = activity_type.strip()
    entry.duration_minutes = duration_minutes
    entry.date = entry_date
    entry.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(entry)
    return entry


def delete_exercise_entry(db: DbSession, entry_id: int) -> bool:
    entry = db.get(ExerciseEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True
