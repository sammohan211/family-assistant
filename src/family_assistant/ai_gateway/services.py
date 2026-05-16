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


def get_interaction(db: DbSession, interaction_id: int) -> AssistantInteraction | None:
    return db.get(AssistantInteraction, interaction_id)
