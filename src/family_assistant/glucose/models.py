"""Blood glucose ORM model.

A per-user time-series of readings, like ``BloodPressureReading`` — but this
module is additionally restricted to a single designated owner at the route
layer (see ``glucose/router.py::require_owner``), not just ownership-scoped.
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date(), index=True)
    reading_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    # mmol/L, one decimal place — the Canadian convention (see migration 0030).
    value_mmol_l: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    context: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship()
