"""Hike router.

Per-user Bruce Trail log (list, new, edit, delete) at ``/hike`` plus a
``/hike/progress`` summary. Part of the Health section of the nav.
"""

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.hike.models import Hike
from family_assistant.hike.services import (
    create_hike,
    delete_hike,
    get_hike,
    list_user_hikes,
    progress,
    update_hike,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/hike",
    tags=["hike"],
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


def _parse_distance(raw: str) -> tuple[Decimal | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, "Distance is required."
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None, "Distance must be a decimal number."
    if value <= 0:
        return None, "Distance must be greater than zero."
    return value, None


def _parse_duration(raw: str) -> tuple[int | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, "Duration is required."
    try:
        value = int(cleaned)
    except ValueError:
        return None, "Duration must be a whole number of minutes."
    if value <= 0:
        return None, "Duration must be greater than zero."
    return value, None


def _render_form(
    request: Request,
    *,
    hike: Hike | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "hike/form.html",
        {
            "hike": hike,
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
    hikes = list_user_hikes(db, user=user)
    return templates.TemplateResponse(request, "hike/list.html", {"hikes": hikes, "user": user})


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@router.get("/progress", response_class=HTMLResponse)
def progress_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    summary = progress(db, user=user)
    return templates.TemplateResponse(
        request, "hike/progress.html", {"summary": summary, "user": user}
    )


# ---------------------------------------------------------------------------
# Create / edit / delete
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request, user: Annotated[User, Depends(require_user)]) -> Response:
    return _render_form(request, hike=None, user=user, error=None)


def _validate_and_save(
    *,
    db: DbSession,
    request: Request,
    user: User,
    hike: Hike | None,
    date_raw: str,
    section: str,
    name: str,
    start_location: str,
    start_time_raw: str,
    end_location: str,
    end_time_raw: str,
    distance_raw: str,
    duration_raw: str,
    notes: str,
) -> Response:
    form_data = {
        "date": date_raw,
        "section": section,
        "name": name,
        "start_location": start_location,
        "start_time": start_time_raw,
        "end_location": end_location,
        "end_time": end_time_raw,
        "distance_km": distance_raw,
        "duration_minutes": duration_raw,
        "notes": notes,
    }

    entry_date, date_error = _parse_date(date_raw)
    start_time, start_time_error = _parse_time(start_time_raw)
    end_time, end_time_error = _parse_time(end_time_raw)
    distance_km, distance_error = _parse_distance(distance_raw)
    duration, duration_error = _parse_duration(duration_raw)

    error = date_error or start_time_error or end_time_error or distance_error or duration_error
    if error is None and not section.strip():
        error = "Section is required."
    if error is None and not name.strip():
        error = "Hike name is required."
    if error is not None:
        return _render_form(
            request, hike=hike, user=user, error=error, form_data=form_data, status_code=400
        )
    assert entry_date is not None and distance_km is not None and duration is not None

    if hike is None:
        create_hike(
            db,
            user=user,
            entry_date=entry_date,
            section=section,
            name=name,
            start_location=start_location or None,
            start_time=start_time,
            end_location=end_location or None,
            end_time=end_time,
            distance_km=distance_km,
            duration_minutes=duration,
            notes=notes or None,
        )
    else:
        update_hike(
            db,
            hike_id=hike.id,
            entry_date=entry_date,
            section=section,
            name=name,
            start_location=start_location or None,
            start_time=start_time,
            end_location=end_location or None,
            end_time=end_time,
            distance_km=distance_km,
            duration_minutes=duration,
            notes=notes or None,
        )
    return RedirectResponse(url="/hike", status_code=303)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    date: Annotated[str, Form()] = "",
    section: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    start_location: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    end_location: Annotated[str, Form()] = "",
    end_time: Annotated[str, Form()] = "",
    distance_km: Annotated[str, Form()] = "",
    duration_minutes: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        hike=None,
        date_raw=date,
        section=section,
        name=name,
        start_location=start_location,
        start_time_raw=start_time,
        end_location=end_location,
        end_time_raw=end_time,
        distance_raw=distance_km,
        duration_raw=duration_minutes,
        notes=notes,
    )


@router.get("/{hike_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    hike_id: int,
) -> Response:
    hike = get_hike(db, hike_id)
    if hike is None or hike.user_id != user.id:
        return RedirectResponse(url="/hike", status_code=303)
    return _render_form(request, hike=hike, user=user, error=None)


@router.post("/{hike_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    hike_id: int,
    date: Annotated[str, Form()] = "",
    section: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    start_location: Annotated[str, Form()] = "",
    start_time: Annotated[str, Form()] = "",
    end_location: Annotated[str, Form()] = "",
    end_time: Annotated[str, Form()] = "",
    distance_km: Annotated[str, Form()] = "",
    duration_minutes: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    hike = get_hike(db, hike_id)
    if hike is None or hike.user_id != user.id:
        return RedirectResponse(url="/hike", status_code=303)
    return _validate_and_save(
        db=db,
        request=request,
        user=user,
        hike=hike,
        date_raw=date,
        section=section,
        name=name,
        start_location=start_location,
        start_time_raw=start_time,
        end_location=end_location,
        end_time_raw=end_time,
        distance_raw=distance_km,
        duration_raw=duration_minutes,
        notes=notes,
    )


@router.post("/{hike_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    hike_id: int,
) -> Response:
    hike = get_hike(db, hike_id)
    if hike is None or hike.user_id != user.id:
        return RedirectResponse(url="/hike", status_code=303)
    delete_hike(db, hike_id)
    return RedirectResponse(url="/hike", status_code=303)
