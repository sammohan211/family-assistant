"""FastAPI dependencies for auth + CSRF (PRD Sections 10.1, 13, 15.1)."""

import secrets
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User, UserSession
from family_assistant.auth.services import get_session_user
from family_assistant.db import get_session

SESSION_COOKIE_NAME = "fa_session"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_EXEMPT_PATHS = frozenset({"/auth/login"})


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


async def require_csrf(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    """Stash the session's CSRF token for templates, and enforce it on unsafe requests.

    Login is exempted because the threat model has no public sign-up and only two
    pre-seeded users, so login CSRF has no exploitable outcome.
    """
    if session_token:
        session = db.get(UserSession, session_token)
        if session is not None and session.csrf_token:
            request.state.csrf_token = session.csrf_token

    if request.method in _SAFE_METHODS or request.url.path in _CSRF_EXEMPT_PATHS:
        return

    expected = getattr(request.state, "csrf_token", None)
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token")

    form = await request.form()
    submitted = form.get("_csrf")
    if not isinstance(submitted, str) or not secrets.compare_digest(submitted, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
