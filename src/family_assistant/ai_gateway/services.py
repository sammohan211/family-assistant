"""Read helpers for AssistantInteraction history."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.ai_gateway.models import AssistantInteraction


def _with_user(statement):
    return statement.options(selectinload(AssistantInteraction.user))


def list_recent_interactions(db: DbSession, limit: int = 20) -> list[AssistantInteraction]:
    statement = (
        select(AssistantInteraction)
        .order_by(AssistantInteraction.created_at.desc(), AssistantInteraction.id.desc())
        .limit(limit)
    )
    return list(db.scalars(_with_user(statement)).all())


def get_interaction(
    db: DbSession, interaction_id: int, *, user_id: int | None = None
) -> AssistantInteraction | None:
    row = db.get(AssistantInteraction, interaction_id)
    if row is None:
        return None
    if user_id is not None and row.user_id != user_id:
        return None
    return row
