"""Family Assistant FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session as DbSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from family_assistant.assistant import router as assistant_router
from family_assistant.auth import router as auth_router
from family_assistant.auth.dependencies import SESSION_COOKIE_NAME, require_csrf
from family_assistant.auth.services import get_session_user, seed_users
from family_assistant.bp import router as bp_router
from family_assistant.dashboard import router as dashboard_router
from family_assistant.db import get_session, get_sessionmaker
from family_assistant.exercise import router as exercise_router
from family_assistant.family_member import router as family_member_router
from family_assistant.grocery import router as grocery_router
from family_assistant.hike import router as hike_router
from family_assistant.household_task import router as household_task_router
from family_assistant.lessons import router as lessons_router
from family_assistant.lunch_plan import router as lunch_plan_router
from family_assistant.meal_plan import router as meal_plan_router
from family_assistant.memory import router as memory_router
from family_assistant.projects import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with get_sessionmaker()() as db:
        seed_users(db)
    yield


app = FastAPI(title="Family Assistant", lifespan=lifespan, dependencies=[Depends(require_csrf)])

# PWA assets (manifest + icons); mounts bypass app dependencies, so these stay public.
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)


@app.exception_handler(StarletteHTTPException)
async def unauthenticated_redirect(request: Request, exc: StarletteHTTPException) -> Response:
    """Send unauthenticated browsers to the login page instead of raw 401 JSON.

    The whole app is server-rendered navigation, so a bare ``{"detail": ...}`` body
    is never useful to show. A missing/expired session (401 from ``require_user``)
    redirects to login and clears any stale cookie; all other errors keep FastAPI's
    default handling.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        redirect = RedirectResponse(url="/auth/login", status_code=303)
        redirect.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return redirect
    return await http_exception_handler(request, exc)


app.include_router(auth_router)
app.include_router(family_member_router)
app.include_router(grocery_router)
app.include_router(meal_plan_router)
app.include_router(lunch_plan_router)
app.include_router(household_task_router)
app.include_router(lessons_router)
app.include_router(projects_router)
app.include_router(exercise_router)
app.include_router(hike_router)
app.include_router(bp_router)
app.include_router(memory_router)
app.include_router(assistant_router)
app.include_router(dashboard_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root(
    db: Annotated[DbSession, Depends(get_session)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> RedirectResponse:
    if session_token and get_session_user(db, session_token) is not None:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)
