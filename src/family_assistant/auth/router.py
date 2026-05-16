"""Auth router (PRD Section 10.1)."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import SESSION_COOKIE_NAME
from family_assistant.auth.services import (
    SESSION_DURATION,
    authenticate,
    create_session,
    delete_session,
)
from family_assistant.db import get_session
from family_assistant.settings import get_settings
from family_assistant.templating import templates

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> Response:
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login")
def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    user = authenticate(db, email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid email or password."},
            status_code=401,
        )
    session = create_session(db, user)
    redirect = RedirectResponse(url="/grocery", status_code=303)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return redirect


@router.post("/logout")
def logout(
    db: Annotated[DbSession, Depends(get_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> Response:
    if session_token:
        delete_session(db, session_token)
    redirect = RedirectResponse(url="/auth/login", status_code=303)
    redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return redirect
