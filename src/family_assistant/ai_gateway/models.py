"""AssistantInteraction ORM model (PRD Sections 11.10, 12)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_assistant.auth.models import User
from family_assistant.db import Base


class AssistantInteraction(Base):
    __tablename__ = "assistant_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    input_text: Mapped[str] = mapped_column(Text())
    parsed_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), nullable=True)
    parsed_entities: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), nullable=True)
    proposed_tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(), nullable=False, default=list, server_default="[]"
    )
    confirmation_status: Mapped[str] = mapped_column(String(20))
    executed_tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(), nullable=False, default=list, server_default="[]"
    )
    affected_record_ids: Mapped[dict[str, list[int]]] = mapped_column(
        JSONB(), nullable=False, default=dict, server_default="{}"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text(), nullable=True)

    user: Mapped[User] = relationship()
