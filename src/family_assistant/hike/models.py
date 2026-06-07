"""Bruce Trail hike ORM model.

A per-user log of trail segments walked. Each row records a named segment
(``section`` + ``name``), start/end map links and times, and persists a
computed ``speed_kmh`` on write so the figure doesn't depend on recomputation
at read time — same approach as ``ExerciseLog.work_score``.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class Hike(Base):
    __tablename__ = "hikes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date(), index=True)
    section: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    start_location: Mapped[str | None] = mapped_column(Text(), nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    end_location: Mapped[str | None] = mapped_column(Text(), nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    distance_km: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    duration_minutes: Mapped[int] = mapped_column(Integer())
    speed_kmh: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
