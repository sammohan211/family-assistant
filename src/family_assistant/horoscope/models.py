"""Horoscope ORM model.

One cached reading per (system, period_type, period_key) — household-shared,
no user scope, and deliberately no birth data: only the generated text plus
provenance (model, generated_at). Rows are written lazily the first time
someone reveals a period (PRD §21 Phase 4: no background generation).
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from family_assistant.db import Base


class HoroscopeReading(Base):
    __tablename__ = "horoscope_readings"
    __table_args__ = (
        UniqueConstraint("system", "period_type", "period_key", name="uq_horoscope_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    system: Mapped[str] = mapped_column(String(16))  # vedic | chinese | western
    period_type: Mapped[str] = mapped_column(String(8), index=True)  # day | week | month | year
    # day "2026-06-12", week "2026-W24", month "2026-06", year "2026"
    period_key: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text())
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
