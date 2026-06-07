"""Blood pressure router.

Per-user reading log (list, new, edit, delete) at ``/bp`` plus a ``/bp/trends``
aggregation view. Part of the Health section of the nav (alongside Exercise and
Hikes).
"""

from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.bp.models import BloodPressureReading
from family_assistant.bp.services import (
    classify,
    create_reading,
    delete_reading,
    get_reading,
    list_user_readings,
    trends,
    update_reading,
)
from family_assistant.db import get_session
from family_assistant.templating import templates

router = APIRouter(
    prefix="/bp",
    tags=["bp"],
    dependencies=[Depends(require_user)],
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


def _parse_optional_int(
    raw: str, label: str, *, low: int, high: int
) -> tuple[int | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, None
    try:
        value = int(cleaned)
    except ValueError:
        return None, f"{label} must be a whole number."
    if not (low <= value <= high):
        return None, f"{label} must be between {low} and {high}."
    return value, None


def _render_form(
    request: Request,
    *,
    reading: BloodPressureReading | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "bp/form.html",
        {
            "reading": reading,
            "user": user,
            "error": error,
            "form_data": form_data or {},
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
    user: Annotated[User, Depends(require_user)],
) -> Response:
    readings = list_user_readings(db, user=user)
    rows = [(r, *classify(r.systolic, r.diastolic)) for r in readings]
    return templates.TemplateResponse(
        request,
        "bp/list.html",
        {"rows": rows, "user": user},
    )


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


@router.get("/trends", response_class=HTMLResponse)
def trends_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    summary = trends(db, user=user)
    latest_category = (
        classify(summary.latest.systolic, summary.latest.diastolic) if summary.latest else None
    )
    return templates.TemplateResponse(
        request,
        "bp/trends.html",
        {"summary": summary, "user": user, "latest_category": latest_category},
    )


# ---------------------------------------------------------------------------
# Create / edit / delete
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request, user: Annotated[User, Depends(require_user)]) -> Response:
    return _render_form(request, reading=None, user=user, error=None)


def _validate_and_save(
    *,
    db: DbSession,
    request: Request,
    user: User,
    reading: BloodPressureReading | None,
    date_raw: str,
    time_raw: str,
    systolic_raw: str,
    diastolic_raw: str,
    heart_rate_raw: str,
    notes: str,
) -> Response:
    form_data = {
        "date": date_raw,
        "reading_time": time_raw,
        "systolic": systolic_raw,
        "diastolic": diastolic_raw,
        "heart_rate": heart_rate_raw,
        "notes": notes,
    }

    entry_date, date_error = _parse_date(date_raw)
    reading_time, time_error = _parse_time(time_raw)
    systolic, sys_error = _parse_required_int(systolic_raw, "Systolic", low=40, high=300)
    diastolic, dia_error = _parse_required_int(diastolic_raw, "Diastolic", low=20, high=200)
    heart_rate, hr_error = _parse_optional_int(heart_rate_raw, "Heart rate", low=20, high=250)

    error = date_error or time_error or sys_error or dia_error or hr_error
    if error is None and systolic is not None and diastolic is not None and diastolic >= systolic:
        error = "Diastolic must be lower than systolic."
    if error is not None:
        return _render_form(
            request,
            reading=reading,
            user=user,
            error=error,
            form_data=form_data,
            status_code=400,
        )
    assert entry_date is not None and systolic is not None and diastolic is not None

    if reading is None:
        create_reading(
            db,
            user=user,
            entry_date=entry_date,
            reading_time=reading_time,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            notes=notes or None,
        )
    else:
        update_reading(
            db,
            reading_id=reading.id,
            entry_date=entry_date,
            reading_time=reading_time,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            notes=notes or None,
        )
    return RedirectResponse(url="/bp", status_code=303)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    date: Annotated[str, Form()] = "",
    reading_time: Annotated[str, Form()] = "",
    systolic: Annotated[str, Form()] = "",
    diastolic: Annotated[str, Form()] = "",
    heart_rate: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        reading=None,
        date_raw=date,
        time_raw=reading_time,
        systolic_raw=systolic,
        diastolic_raw=diastolic,
        heart_rate_raw=heart_rate,
        notes=notes,
    )


@router.get("/{reading_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    reading_id: int,
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/bp", status_code=303)
    return _render_form(request, reading=reading, user=user, error=None)


@router.post("/{reading_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    reading_id: int,
    date: Annotated[str, Form()] = "",
    reading_time: Annotated[str, Form()] = "",
    systolic: Annotated[str, Form()] = "",
    diastolic: Annotated[str, Form()] = "",
    heart_rate: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/bp", status_code=303)
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        reading=reading,
        date_raw=date,
        time_raw=reading_time,
        systolic_raw=systolic,
        diastolic_raw=diastolic,
        heart_rate_raw=heart_rate,
        notes=notes,
    )


@router.post("/{reading_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    reading_id: int,
) -> Response:
    reading = get_reading(db, reading_id)
    if reading is None or reading.user_id != user.id:
        return RedirectResponse(url="/bp", status_code=303)
    delete_reading(db, reading_id)
    return RedirectResponse(url="/bp", status_code=303)
