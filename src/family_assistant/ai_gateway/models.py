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
    reply: Mapped[str] = mapped_column(Text(), nullable=False, default="", server_default="")
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


class InteractionTrace(Base):
    """Per-stage observability for AI Gateway runs.

    One row per stage event inside a `process_command` / `confirm_pending` /
    `cancel_pending` call. The (stage, event) pair names *which layer* made
    *which decision* — that's the architectural literacy this gives back when
    debugging assistant misbehavior. Payload is free-form JSONB so call sites
    don't need a migration to record new fields.
    """

    __tablename__ = "interaction_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    interaction_id: Mapped[int] = mapped_column(
        ForeignKey("assistant_interactions.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Monotonic offset (ms) from the start of the orchestrating call. Cheaper
    # than diffing created_at across rows and survives clock skew.
    ts_ms: Mapped[int] = mapped_column(Integer(), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(), nullable=False, default=dict, server_default="{}"
    )

    interaction: Mapped[AssistantInteraction] = relationship()
