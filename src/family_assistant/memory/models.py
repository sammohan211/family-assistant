"""Memory ORM model (PRD Sections 11.7, 12)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text())
    is_hard_restriction: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default="false"
    )
    source: Mapped[str] = mapped_column(String(30), default="user", server_default="user")
    tags: Mapped[list[str]] = mapped_column(
        JSONB(), nullable=False, default=list, server_default="[]"
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by_user: Mapped[User | None] = relationship()

    __table_args__ = (
        Index("ix_memories_subject", "subject_type", "subject_id"),
        Index("ix_memories_memory_type", "memory_type"),
    )
