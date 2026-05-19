"""Grocery ORM models (PRD Section 10.4)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base

GroceryStatus = Literal["open", "purchased"]


class GroceryItem(Base):
    __tablename__ = "grocery_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[GroceryStatus] = mapped_column(String(20), default="open", server_default="open")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    added_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purchased_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    added_by_user: Mapped[User] = relationship(foreign_keys=[added_by_user_id])
    purchased_by_user: Mapped[User | None] = relationship(foreign_keys=[purchased_by_user_id])
