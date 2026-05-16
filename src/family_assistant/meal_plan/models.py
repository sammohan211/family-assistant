"""Meal planning ORM models (PRD Section 10.5)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date())
    meal_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(140))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="false"
    )
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by_user: Mapped[User] = relationship()
