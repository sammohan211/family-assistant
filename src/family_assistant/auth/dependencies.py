"""FastAPI dependencies for auth (PRD Section 10.1 / 13)."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User
from family_assistant.auth.services import get_session_user
from family_assistant.db import get_session

SESSION_COOKIE_NAME = "fa_session"


def require_user(
    db: Annotated[DbSession, Depends(get_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    if session_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = get_session_user(db, session_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        )
    return user
