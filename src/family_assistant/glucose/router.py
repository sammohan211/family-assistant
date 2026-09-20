"""Blood glucose router.

Per-user reading log (list, new, edit, delete) at ``/glucose`` plus a
``/glucose/trends`` view with a small Chart.js chart. Part of the Health
section of the nav, but **restricted to a single designated owner**
(``settings.user1_email``) — unlike BP/Hikes, which are ownership-scoped but
reachable by either adult, every route here 404s (not 403, to avoid revealing
the module exists) for anyone else. The nav entry itself is hidden for
non-owners too (see ``templating.py``'s ``is_glucose_owner`` global) but that
is UX only — ``require_owner`` is the real gate.
"""

from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.glucose.models import GlucoseReading
from family_assistant.glucose.services import (
    CONTEXT_HELP,
    CONTEXT_LABELS,
    CONTEXTS,
    classify,
    create_reading,
    delete_reading,
    get_reading,
    list_user_readings,
    trends,
    update_reading,
)
from family_assistant.settings import get_settings
from family_assistant.templating import templates


def require_owner(user: Annotated[User, Depends(require_user)]) -> User:
    """404s (not 403) for anyone but the designated owner — hides the module's existence."""
    if user.email != get_settings().user1_email:
        raise HTTPException(status_code=404)
    return user


router = APIRouter(
    prefix="/glucose",
    tags=["glucose"],
    dependencies=[Depends(require_owner)],
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> tuple[date | None, str | None]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None, "Date is required."
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Date must be YYYY-MM-DD."


def _parse_time(value: str) -> tuple[time | None, str | None]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None, None
    try:
        return datetime.strptime(cleaned, "%H:%M").time(), None
    except ValueError:
        return None, "Time must be HH:MM."


def _parse_required_int(
    raw: str, label: str, *, low: int, high: int
) -> tuple[int | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, f"{label} is required."
    try:
        value = int(cleaned)
    except ValueError:
        return None, f"{label} must be a whole number."
    if not (low <= value <= high):
        return None, f"{label} must be between {low} and {high}."
    return value, None


def _parse_context(raw: str) -> tuple[str | None, str | None]:
    cleaned = (raw or "").strip()
    if cleaned not in CONTEXTS:
        return None, "Choose a valid reading context."
    return cleaned, None


def _render_form(
    request: Request,
    *,
    reading: GlucoseReading | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "glucose/form.html",
        {
            "reading": reading,
            "user": user,
            "error": error,
            "form_data": form_data or {},
            "contexts": CONTEXTS,
            "context_labels": CONTEXT_LABELS,
            "context_help": CONTEXT_HELP,
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
) -> Response:
    readings = list_user_readings(db, user=user)
    rows = [(r, *classify(r.value_mg_dl, r.context)) for r in readings]
    return templates.TemplateResponse(
        request,
        "glucose/list.html",
        {"rows": rows, "user": user, "context_labels": CONTEXT_LABELS},
    )


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


@router.get("/trends", response_class=HTMLResponse)
def trends_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
) -> Response:
    summary = trends(db, user=user)
    latest_category = (
        classify(summary.latest.value_mg_dl, summary.latest.context) if summary.latest else None
    )
    return templates.TemplateResponse(
        request,
        "glucose/trends.html",
        {
            "summary": summary,
            "user": user,
            "latest_category": latest_category,
            "context_labels": CONTEXT_LABELS,
        },
    )


# ---------------------------------------------------------------------------
# Create / edit / delete
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request, user: Annotated[User, Depends(require_owner)]) -> Response:
    return _render_form(request, reading=None, user=user, error=None)


def _validate_and_save(
    *,
    db: DbSession,
    request: Request,
    user: User,
    reading: GlucoseReading | None,
    date_raw: str,
    time_raw: str,
    value_raw: str,
    context_raw: str,
    notes: str,
) -> Response:
    form_data = {
        "date": date_raw,
        "reading_time": time_raw,
        "value_mg_dl": value_raw,
        "context": context_raw,
        "notes": notes,
    }

    entry_date, date_error = _parse_date(date_raw)
    reading_time, time_error = _parse_time(time_raw)
    value, value_error = _parse_required_int(value_raw, "Reading", low=20, high=600)
    context, context_error = _parse_context(context_raw)

    error = date_error or time_error or value_error or context_error
    if error is not None:
        return _render_form(
            request,
            reading=reading,
            user=user,
            error=error,
            form_data=form_data,
            status_code=400,
        )
    assert entry_date is not None and value is not None and context is not None

    if reading is None:
        create_reading(
            db,
            user=user,
            entry_date=entry_date,
            reading_time=reading_time,
            value_mg_dl=value,
            context=context,
            notes=notes or None,
        )
    else:
        update_reading(
            db,
            reading_id=reading.id,
            entry_date=entry_date,
            reading_time=reading_time,
            value_mg_dl=value,
            context=context,
            notes=notes or None,
        )
    return RedirectResponse(url="/glucose", status_code=303)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
    date: Annotated[str, Form()] = "",
    reading_time: Annotated[str, Form()] = "",
    value_mg_dl: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        reading=None,
        date_raw=date,
        time_raw=reading_time,
        value_raw=value_mg_dl,
        context_raw=context,
        notes=notes,
    )


@router.get("/{reading_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
    reading_id: int,
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/glucose", status_code=303)
    return _render_form(request, reading=reading, user=user, error=None)


@router.post("/{reading_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
    reading_id: int,
    date: Annotated[str, Form()] = "",
    reading_time: Annotated[str, Form()] = "",
    value_mg_dl: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/glucose", status_code=303)
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        reading=reading,
        date_raw=date,
        time_raw=reading_time,
        value_raw=value_mg_dl,
        context_raw=context,
        notes=notes,
    )


@router.post("/{reading_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_owner)],
    reading_id: int,
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/glucose", status_code=303)
    delete_reading(db, reading_id)
    return RedirectResponse(url="/glucose", status_code=303)
