"""Family Assistant FastAPI app."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.assistant import router as assistant_router
from family_assistant.auth import router as auth_router
from family_assistant.auth.dependencies import SESSION_COOKIE_NAME, require_csrf
from family_assistant.auth.services import get_session_user, seed_users
from family_assistant.dashboard import router as dashboard_router
from family_assistant.db import SessionLocal, get_session
from family_assistant.exercise import router as exercise_router
from family_assistant.family_member import router as family_member_router
from family_assistant.grocery import router as grocery_router
from family_assistant.lunch_plan import router as lunch_plan_router
from family_assistant.meal_plan import router as meal_plan_router
from family_assistant.memory import router as memory_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        seed_users(db)
    yield


app = FastAPI(title="Family Assistant", lifespan=lifespan, dependencies=[Depends(require_csrf)])

app.include_router(auth_router)
app.include_router(family_member_router)
app.include_router(grocery_router)
app.include_router(meal_plan_router)
app.include_router(lunch_plan_router)
app.include_router(exercise_router)
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
        return RedirectResponse(url="/grocery", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)
