"""Meal planning ORM models (PRD Section 10.5).

Two tables: a household-shared catalog of reusable ``Recipe`` rows (the meal
counterpart to the exercise catalog) and the dated ``MealPlanEntry`` rows that
schedule meals onto the calendar. A plan entry references a recipe only by its
free-text title, so recipes can be edited or removed without breaking history.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class Recipe(Base):
    """Household-shared catalog of reusable recipes for meal planning.

    Macros are intentionally coarse and nullable — they're a planning aid, not
    a tracking ledger. ``ingredients`` is a flat list of names so the assistant
    can match a recipe against what's currently on the grocery list / on hand.
    """

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), unique=True)
    meal_type: Mapped[str] = mapped_column(String(20))
    ingredients: Mapped[list[str]] = mapped_column(JSONB(), default=list, server_default="[]")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    calories: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    protein_g: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
