"""Horoscope router.

Household-shared, common-area pages at ``/horoscope``: a landing grid of the
eight periods, a per-period view, and a POST reveal action that does the lazy
generate-and-cache. Shows horoscope text only — no birth data exists anywhere
in the app to show.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.llm import LLMClient, default_client
from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.horoscope.natal import load_natal_facts
from family_assistant.horoscope.services import (
    PERIOD_LABELS,
    SYSTEMS,
    CannedHoroscopeLLM,
    HoroscopeGenerationError,
    cached_period_keys,
    cached_readings,
    generate_readings,
    resolve_period,
)
from family_assistant.settings import get_settings
from family_assistant.templating import templates

router = APIRouter(
    prefix="/horoscope",
    tags=["horoscope"],
    dependencies=[Depends(require_user)],
)

# Display order for the three reading cards.
SYSTEM_TITLES = (
    ("vedic", "Vedic", "Jyotish · sidereal, gochara from the moon"),
    ("chinese", "Chinese", "Year pillars · sexagenary cycle"),
    ("western", "Western", "Tropical · transits from the ascendant"),
)


def get_horoscope_llm() -> LLMClient:
    if get_settings().use_mock_llm:
        return CannedHoroscopeLLM()
    return default_client()


def _model_label() -> str | None:
    settings = get_settings()
    if settings.use_mock_llm:
        return "mock"
    if settings.llm_provider == "openrouter":
        return settings.openrouter_model
    return settings.ollama_model


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    natal = load_natal_facts()
    periods = [resolve_period(token) for token in PERIOD_LABELS]
    ready = cached_period_keys(db) if natal is not None else set()
    return templates.TemplateResponse(
        request,
        "horoscope/index.html",
        {
            "user": user,
            "natal_missing": natal is None,
            "periods": periods,
            "ready_keys": ready,
        },
    )


@router.get("/{token}", response_class=HTMLResponse)
def period_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    token: str,
    error: str | None = None,
) -> Response:
    if token not in PERIOD_LABELS or load_natal_facts() is None:
        return RedirectResponse(url="/horoscope", status_code=303)
    spec = resolve_period(token)
    readings = cached_readings(db, spec)
    complete = all(system in readings for system in SYSTEMS)
    return templates.TemplateResponse(
        request,
        "horoscope/period.html",
        {
            "user": user,
            "spec": spec,
            "tokens": PERIOD_LABELS,
            "readings": readings,
            "complete": complete,
            "system_titles": SYSTEM_TITLES,
            "error": error,
        },
    )


@router.post("/{token}/reveal")
def reveal(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    token: str,
    llm: Annotated[LLMClient, Depends(get_horoscope_llm)],
) -> Response:
    natal = load_natal_facts()
    if token not in PERIOD_LABELS or natal is None:
        return RedirectResponse(url="/horoscope", status_code=303)
    spec = resolve_period(token)
    try:
        generate_readings(db, llm=llm, natal=natal, spec=spec, model_label=_model_label())
    except HoroscopeGenerationError as exc:
        return period_view(request, db, user, token, error=str(exc))
    return RedirectResponse(url=f"/horoscope/{token}", status_code=303)
