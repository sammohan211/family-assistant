"""Projects-tracker ORM models (PRD Section 21, Phase 4 item 2).

A per-user, **private** space for an adult to track their own initiatives —
learning projects, side projects, anything kept separate from shared household
operations. Each project belongs to exactly one user and is never visible to
other household members (unlike Lessons / Tasks, which are household-shared).

Three tables, reusing the app's container + nested-items + journal pattern:

  - ``Project`` — the container: a ``name``, a lifecycle ``status``, an optional
    ``goal`` and ``target_date``.
  - ``ProjectMilestone`` — an ordered, optionally-dated breakdown checkpoint.
    Completing one auto-writes a journal entry (see services.toggle_milestone).
  - ``ProjectEntry`` — the journal/timeline: a dated note with an optional link.

Milestones carry optional due dates but **no subtasks and no recurrence**
(anything recurring belongs to Household Tasks). The project's ``status`` is set
manually via the edit form — milestones do not auto-complete the project.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base

# Project lifecycle. "active" is the working default; "done"/"abandoned" stay
# browsable but collapse out of the active view.
PROJECT_STATUSES: tuple[str, ...] = ("idea", "active", "on_hold", "done", "abandoned")

# Statuses that count as "finished" — collapsed below active projects and
# exempt from the stale-project nudge.
CLOSED_STATUSES: tuple[str, ...] = ("done", "abandoned")

STATUS_LABELS: dict[str, str] = {
    "idea": "Idea",
    "active": "Active",
    "on_hold": "On hold",
    "done": "Done",
    "abandoned": "Abandoned",
}

# An active project with no entry / milestone completion in this many days is
# flagged "stale" in the list (a light nudge; richer surfacing can come later).
STALE_AFTER_DAYS = 21


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    goal: Mapped[str | None] = mapped_column(Text(), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
    milestones: Mapped[list["ProjectMilestone"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectMilestone.position, ProjectMilestone.id",
    )
    entries: Mapped[list["ProjectEntry"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectEntry.entry_date.desc(), ProjectEntry.id.desc()",
    )

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    @property
    def milestones_total(self) -> int:
        return len(self.milestones)

    @property
    def milestones_done(self) -> int:
        return sum(1 for m in self.milestones if m.done)

    @property
    def last_touched(self) -> date | None:
        """Most recent sign of life: latest journal entry or milestone
        completion. Drives the stale-project signal."""
        candidates: list[date] = [e.entry_date for e in self.entries]
        candidates += [m.done_at.date() for m in self.milestones if m.done and m.done_at]
        return max(candidates) if candidates else None

    def is_stale(self, today: date) -> bool:
        """An active/idea/on-hold project untouched for STALE_AFTER_DAYS days.
        Closed projects are never stale."""
        if self.is_closed:
            return False
        touched = self.last_touched
        if touched is None:
            # Fall back to creation date so brand-new empty projects aren't
            # instantly flagged, but long-empty ones eventually are.
            touched = self.created_at.date() if self.created_at else today
        return (today - touched).days >= STALE_AFTER_DAYS


class ProjectMilestone(Base):
    __tablename__ = "project_milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    target_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="milestones")


class ProjectEntry(Base):
    __tablename__ = "project_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    entry_date: Mapped[date] = mapped_column(Date(), index=True)
    note: Mapped[str] = mapped_column(Text())
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Auto-written journal lines (milestone completions) carry the milestone id
    # so un-completing can remove its line; manual notes leave this NULL.
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="entries")

    @property
    def is_auto(self) -> bool:
        return self.milestone_id is not None
