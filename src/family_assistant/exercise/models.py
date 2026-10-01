"""Exercise ORM models (PRD Section 10.7).

Two tables: a household-shared catalog of named exercises and a per-user
log of sessions. Each log row carries a persisted ``work_score`` so prior
comparisons don't drift when a user updates their body weight, plus the
``body_weight_used`` for that score so an edit re-scores with the same weight.

Catalog muscles, region, modality and location use the fixed vocabulary in
:mod:`exercise.taxonomy` (PRD §10.16).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    region: Mapped[str] = mapped_column(String(16))
    modality: Mapped[str] = mapped_column(String(16))
    location: Mapped[str] = mapped_column(String(8))
    primary_muscles: Mapped[list[str]] = mapped_column(JSONB(), default=list, server_default="[]")
    secondary_muscles: Mapped[list[str]] = mapped_column(JSONB(), default=list, server_default="[]")
    scoring_type: Mapped[str] = mapped_column(String(24))
    bodyweight_fraction: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("1.000"), server_default="1.000"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExerciseLog(Base):
    __tablename__ = "exercise_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="RESTRICT"), index=True
    )
    date: Mapped[date] = mapped_column(Date(), index=True)
    sets: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(7, 3), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    work_score: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default="0")
    body_weight_used: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
    exercise: Mapped[Exercise] = relationship()


class TrainingWeekSummary(Base):
    """Stored snapshot of one user's completed ISO week (PRD §10.16 step 2).

    Built lazily by :mod:`exercise.summary` the first time a completed week is
    requested; deleted whenever a log in that week (or any catalog entry) changes,
    so it is rebuilt on next use. ``data`` carries its own ``version``.
    """

    __tablename__ = "training_week_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_training_week_summaries_user_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date())
    data: Mapped[dict] = mapped_column(JSONB())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingPriorities(Base):
    """One user's training priorities for one ISO week (PRD §10.16 step 3).

    Written by the card's "Get AI tips" button, which calls the LLM at most once
    per week: once a row has a usable answer (``model`` set, not
    ``is_fallback``) no further calls are made; a failed attempt may be retried
    and overwrites it. ``content`` holds the validated LLM answer, or the
    deterministic ranking when ``is_fallback`` is true. The card itself is
    rebuilt from the live ranking on every view and only borrows this wording.
    """

    __tablename__ = "training_priorities"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_training_priorities_user_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date())
    content: Mapped[dict] = mapped_column(JSONB())
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_fallback: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
