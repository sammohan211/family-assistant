"""Blood pressure ORM model.

A per-user time-series of readings. Each row carries a persisted ``map_value``
(mean arterial pressure) computed on write so trends don't depend on a
derived field being recomputed at read time — mirrors how ``ExerciseLog``
persists its ``work_score``.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class BloodPressureReading(Base):
    __tablename__ = "blood_pressure_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date(), index=True)
    reading_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    systolic: Mapped[int] = mapped_column(Integer())
    diastolic: Mapped[int] = mapped_column(Integer())
    heart_rate: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    map_value: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
