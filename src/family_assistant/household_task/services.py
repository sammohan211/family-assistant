"""Household task CRUD + completion services (PRD Section 21, Phase 4 item 1).

All tasks are household-shared, so reads/writes are not scoped to a user.
Completing a task appends a :class:`HouseholdTaskCompletion` row and either
archives a one-off task or rolls a recurring task's ``next_due_date`` forward
**from the completion date** (so chores done a little late don't pile up).
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.household_task.models import (
    FREQUENCY_UNITS,
    HouseholdTask,
    HouseholdTaskCompletion,
)

# ---------------------------------------------------------------------------
# Recurrence
# ---------------------------------------------------------------------------


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance_due_date(start: date, unit: str, count: int) -> date:
    """Next due date ``count`` units after ``start``. ``once`` has no next date."""
    if unit == "day":
        return start + timedelta(days=count)
    if unit == "week":
        return start + timedelta(weeks=count)
    if unit == "month":
        return _add_months(start, count)
    raise ValueError(f"Cannot advance a {unit!r} task")


# ---------------------------------------------------------------------------
# Users (assignee picker)
# ---------------------------------------------------------------------------


def list_users(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.name.asc())).all())


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


def _with_assignee(statement):
    return statement.options(
        selectinload(HouseholdTask.assignee),
        selectinload(HouseholdTask.last_completed_by),
    )


def list_active_tasks(db: DbSession) -> list[HouseholdTask]:
    """Active tasks, soonest-due first (overdue floats to the top)."""
    statement = (
        select(HouseholdTask)
        .where(HouseholdTask.active.is_(True))
        .order_by(HouseholdTask.next_due_date.asc(), HouseholdTask.name.asc())
    )
    return list(db.scalars(_with_assignee(statement)).all())


def get_task(db: DbSession, task_id: int) -> HouseholdTask | None:
    statement = select(HouseholdTask).where(HouseholdTask.id == task_id)
    return db.scalars(_with_assignee(statement)).first()


def create_task(
    db: DbSession,
    *,
    name: str,
    details: str | None,
    assignee_id: int | None,
    frequency_unit: str,
    frequency_count: int,
    next_due_date: date,
) -> HouseholdTask:
    if frequency_unit not in FREQUENCY_UNITS:
        raise ValueError(f"Unknown frequency_unit: {frequency_unit!r}")
    task = HouseholdTask(
        name=name.strip(),
        details=details.strip() if details else None,
        assignee_id=assignee_id,
        frequency_unit=frequency_unit,
        frequency_count=max(1, frequency_count),
        next_due_date=next_due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(
    db: DbSession,
    *,
    task_id: int,
    name: str,
    details: str | None,
    assignee_id: int | None,
    frequency_unit: str,
    frequency_count: int,
    next_due_date: date,
    active: bool,
) -> HouseholdTask | None:
    if frequency_unit not in FREQUENCY_UNITS:
        raise ValueError(f"Unknown frequency_unit: {frequency_unit!r}")
    task = db.get(HouseholdTask, task_id)
    if task is None:
        return None
    task.name = name.strip()
    task.details = details.strip() if details else None
    task.assignee_id = assignee_id
    task.frequency_unit = frequency_unit
    task.frequency_count = max(1, frequency_count)
    task.next_due_date = next_due_date
    task.active = active
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: DbSession, task_id: int) -> bool:
    task = db.get(HouseholdTask, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------


def complete_task(
    db: DbSession,
    *,
    task: HouseholdTask,
    user: User,
    today: date | None = None,
) -> HouseholdTask:
    """Log a completion, then archive (one-off) or reschedule (recurring)."""
    today = today or date.today()
    completion = HouseholdTaskCompletion(
        task_id=task.id,
        completed_by_id=user.id,
        due_on=task.next_due_date,
    )
    db.add(completion)

    task.last_completed_at = datetime.now(UTC)
    task.last_completed_by_id = user.id
    if task.frequency_unit == "once":
        task.active = False
    else:
        task.next_due_date = advance_due_date(today, task.frequency_unit, task.frequency_count)

    db.commit()
    db.refresh(task)
    return task


def list_recent_completions(db: DbSession, *, limit: int = 50) -> list[HouseholdTaskCompletion]:
    statement = (
        select(HouseholdTaskCompletion)
        .order_by(HouseholdTaskCompletion.completed_at.desc(), HouseholdTaskCompletion.id.desc())
        .limit(limit)
        .options(
            selectinload(HouseholdTaskCompletion.task),
            selectinload(HouseholdTaskCompletion.completed_by),
        )
    )
    return list(db.scalars(statement).all())


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------


@dataclass
class TaskCounts:
    overdue: int
    due_today: int
    upcoming: int


def summarize(tasks: list[HouseholdTask], *, today: date | None = None) -> TaskCounts:
    today = today or date.today()
    overdue = sum(1 for t in tasks if t.next_due_date < today)
    due_today = sum(1 for t in tasks if t.next_due_date == today)
    upcoming = sum(1 for t in tasks if t.next_due_date > today)
    return TaskCounts(overdue=overdue, due_today=due_today, upcoming=upcoming)
