"""Assistant input router (PRD Section 14.3 / 11)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway import cancel_pending, confirm_pending, process_command
from family_assistant.ai_gateway.llm import LLMClient
from family_assistant.ai_gateway.services import get_interaction, list_recent_interactions
from family_assistant.assistant.dependencies import get_llm
from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.templating import templates

router = APIRouter(
    prefix="/assistant",
    tags=["assistant"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    recent = list_recent_interactions(db, user_id=user.id, limit=10)
    latest = recent[0] if recent else None
    history = recent[1:] if latest else []
    return templates.TemplateResponse(
        request,
        "assistant/index.html",
        {"latest": latest, "history": history},
    )


@router.post("")
def submit(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    llm: Annotated[LLMClient, Depends(get_llm)],
    input_text: Annotated[str, Form()],
) -> Response:
    if input_text.strip():
        process_command(user, input_text.strip(), db, llm=llm)
    return RedirectResponse(url="/assistant", status_code=303)


@router.post("/{interaction_id}/confirm")
def confirm(
    interaction_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    interaction = get_interaction(db, interaction_id, user_id=user.id)
    if interaction is not None:
        confirm_pending(interaction, db, user)
    return RedirectResponse(url="/assistant", status_code=303)


@router.post("/{interaction_id}/cancel")
def cancel(
    interaction_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    interaction = get_interaction(db, interaction_id, user_id=user.id)
    if interaction is not None:
        cancel_pending(interaction, db)
    return RedirectResponse(url="/assistant", status_code=303)
