"""Household task ORM models (PRD Section 21, Phase 4 item 1).

Two tables, both **household-shared** (not per-user) — distinguishing chores
from the personal logs (exercise / BP / hikes):

  - ``HouseholdTask`` — the recurring chore definition plus its scheduling
    state (``next_due_date`` and a denormalized "last completed" snapshot for
    quick display). One-off tasks (``frequency_unit == "once"``) archive on
    completion; recurring tasks roll ``next_due_date`` forward.
  - ``HouseholdTaskCompletion`` — an append-only log of who finished a task
    and when (the dated-entries pattern), so the household keeps a history.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base

# Recurrence units. "once" means a one-off task with no repeat (archived when
# completed); the others repeat every ``frequency_count`` units.
FREQUENCY_UNITS: tuple[str, ...] = ("once", "day", "week", "month")


class HouseholdTask(Base):
    __tablename__ = "household_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    details: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # Sticky assignee: an adult (User). Nullable = unassigned / anyone.
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    frequency_unit: Mapped[str] = mapped_column(String(8))
    frequency_count: Mapped[int] = mapped_column(Integer(), default=1, server_default="1")
    next_due_date: Mapped[date] = mapped_column(Date(), index=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_completed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    last_completed_by: Mapped[User | None] = relationship(foreign_keys=[last_completed_by_id])

    @property
    def frequency_label(self) -> str:
        if self.frequency_unit == "once":
            return "One-off"
        if self.frequency_count == 1:
            return {"day": "Daily", "week": "Weekly", "month": "Monthly"}[self.frequency_unit]
        return f"Every {self.frequency_count} {self.frequency_unit}s"


class HouseholdTaskCompletion(Base):
    __tablename__ = "household_task_completions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("household_tasks.id", ondelete="CASCADE"), index=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The due date this completion satisfied — preserves history even after the
    # task's own next_due_date rolls forward.
    due_on: Mapped[date | None] = mapped_column(Date(), nullable=True)

    task: Mapped[HouseholdTask] = relationship()
    completed_by: Mapped[User | None] = relationship()
