"""Exercise ORM models (PRD Section 10.7).

Two tables: a household-shared catalog of named exercises and a per-user
log of sessions. Each log row carries a persisted ``work_score`` so prior
comparisons don't drift when a user updates their body weight.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    body_group: Mapped[str] = mapped_column(String(16))
    muscle_groups: Mapped[list[str]] = mapped_column(JSONB(), default=list, server_default="[]")
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
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
    exercise: Mapped[Exercise] = relationship()
