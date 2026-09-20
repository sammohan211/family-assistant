"""Blood glucose ORM model.

A per-user time-series of readings, like ``BloodPressureReading`` — but this
module is additionally restricted to a single designated owner at the route
layer (see ``glucose/router.py::require_owner``), not just ownership-scoped.
"""

from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date(), index=True)
    reading_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    value_mg_dl: Mapped[int] = mapped_column(Integer())
    context: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
