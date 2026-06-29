"""Lessons-plan ORM models (PRD Section 21, Phase 4 item 3).

A parent-curated home-learning plan, built to keep one kid occupied over the
summer holidays. The kid never logs in — adults populate the plan and tick
items off as the kid completes them. There is only ever one kid in this
household, so lessons are plain household-level rows with **no FamilyMember
link** (decided 2026-06-29).

Four tables, mirroring the app's container + nested-items + check-off pattern:

  - ``Lesson`` — the major unit (a subject/topic block) plus its ``status``.
  - ``LearningObjective`` — an ordered checklist item under a lesson, with an
    optional ``scheduled_date`` so objectives can be spread day-to-day.
  - ``LessonResource`` — a worksheet / video / book link attached to a lesson
    or (optionally) to a single objective.
  - ``LessonTest`` — **exactly one per lesson**. Checking it off is what marks
    the lesson done; a lesson can't be complete without its test.
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

from family_assistant.db import Base

# Lesson lifecycle. "done" is reserved — it is only ever set by completing the
# lesson's test (see services.toggle_test); the edit form offers the other two.
LESSON_STATUSES: tuple[str, ...] = ("planned", "in_progress", "done")
EDITABLE_STATUSES: tuple[str, ...] = ("planned", "in_progress")

STATUS_LABELS: dict[str, str] = {
    "planned": "Planned",
    "in_progress": "In progress",
    "done": "Done",
}


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    subject: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default="planned")
    # Optional summer window.
    start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    objectives: Mapped[list["LearningObjective"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LearningObjective.position, LearningObjective.id",
    )
    resources: Mapped[list["LessonResource"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonResource.position, LessonResource.id",
    )
    test: Mapped["LessonTest | None"] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def objectives_total(self) -> int:
        return len(self.objectives)

    @property
    def objectives_done(self) -> int:
        return sum(1 for o in self.objectives if o.done)

    @property
    def has_test(self) -> bool:
        return self.test is not None

    @property
    def is_complete(self) -> bool:
        return self.test is not None and self.test.done


class LearningObjective(Base):
    __tablename__ = "learning_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    done: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional day-to-day scheduling — a light date only, NOT a calendar.
    scheduled_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    position: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped[Lesson] = relationship(back_populates="objectives")


class LessonResource(Base):
    __tablename__ = "lesson_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    # Optionally pin a resource to one objective; NULL = lesson-level resource.
    objective_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_objectives.id", ondelete="CASCADE"), nullable=True, index=True
    )
    label: Mapped[str] = mapped_column(String(150))
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    position: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped[Lesson] = relationship(back_populates="resources")


class LessonTest(Base):
    __tablename__ = "lesson_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One test per lesson — the unique constraint enforces it at the DB level.
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, index=True
    )
    title: Mapped[str] = mapped_column(String(150))
    done: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lesson: Mapped[Lesson] = relationship(back_populates="test")
