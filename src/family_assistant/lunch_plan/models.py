"""School lunch planning ORM models (PRD Section 10.6)."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base
from family_assistant.family_member.models import FamilyMember


class LunchPlanEntry(Base):
    __tablename__ = "lunch_plan_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_member_id: Mapped[int] = mapped_column(ForeignKey("family_members.id"), index=True)
    date: Mapped[date] = mapped_column(Date())
    items: Mapped[list[dict[str, str]]] = mapped_column(JSONB(), default=list)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    packed_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned", server_default="planned"
    )
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    family_member: Mapped[FamilyMember] = relationship()
    created_by_user: Mapped[User] = relationship()
