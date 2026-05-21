"""Read helpers for AssistantInteraction history."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.ai_gateway.models import AssistantInteraction, InteractionTrace


def _with_user(statement):
    return statement.options(selectinload(AssistantInteraction.user))


def list_recent_interactions(
    db: DbSession, *, user_id: int, limit: int = 20
) -> list[AssistantInteraction]:
    statement = (
        select(AssistantInteraction)
        .where(AssistantInteraction.user_id == user_id)
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


def list_traces_for_interaction(db: DbSession, interaction_id: int) -> list[InteractionTrace]:
    """Per-stage trace rows for one interaction, ordered by request time.

    Caller must scope to the owning user *before* calling this — fetch the
    AssistantInteraction with `get_interaction(..., user_id=...)` first and
    only pass the id if it returned non-None. This keeps the cross-user
    isolation in one place (`get_interaction`) instead of duplicating the
    user_id join here.
    """
    statement = (
        select(InteractionTrace)
        .where(InteractionTrace.interaction_id == interaction_id)
        .order_by(InteractionTrace.ts_ms, InteractionTrace.id)
    )
    return list(db.scalars(statement).all())
