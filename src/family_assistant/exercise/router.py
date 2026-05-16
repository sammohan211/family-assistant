"""Exercise router (PRD Section 10.7)."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.exercise.models import ExerciseEntry
from family_assistant.exercise.services import (
    create_exercise_entry,
    delete_exercise_entry,
    get_exercise_entry,
    list_exercise_entries,
    update_exercise_entry,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/exercise",
    tags=["exercise"],
    dependencies=[Depends(require_user)],
)


def _parse_date(value: str) -> tuple[date | None, str | None]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Date must be in YYYY-MM-DD format."


def _parse_duration(value: str) -> tuple[int | None, str | None]:
    if not value.strip():
        return None, "Duration is required."
    try:
        duration = int(value)
    except ValueError:
        return None, "Duration must be a whole number."
    if duration <= 0:
        return None, "Duration must be greater than zero."
    return duration, None


def _render_form(
    request: Request,
    *,
    item: ExerciseEntry | None,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "exercise/form.html",
        {"item": item, "error": error, "form_data": form_data or {}},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    return templates.TemplateResponse(
        request,
        "exercise/list.html",
        {"entries": list_exercise_entries(db)},
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request) -> Response:
    return _render_form(
        request,
        item=None,
        error=None,
        form_data={"date": date.today().isoformat()},
    )


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    activity_type: Annotated[str, Form()],
    duration_minutes: Annotated[str, Form()],
    exercise_date: Annotated[str, Form(alias="date")],
    notes: Annotated[str, Form()] = "",
) -> Response:
    form_data = {
        "activity_type": activity_type,
        "duration_minutes": duration_minutes,
        "date": exercise_date,
        "notes": notes,
    }
    if not activity_type.strip():
        return _render_form(
            request,
            item=None,
            error="Activity type is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_duration, duration_error = _parse_duration(duration_minutes)
    if duration_error:
        return _render_form(
            request,
            item=None,
            error=duration_error,
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(exercise_date)
    if date_error:
        return _render_form(
            request,
            item=None,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    create_exercise_entry(
        db,
        user=user,
        activity_type=activity_type,
        duration_minutes=parsed_duration,
        entry_date=parsed_date,
        notes=notes,
    )
    return RedirectResponse(url="/exercise", status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_exercise_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/exercise", status_code=303)
    return _render_form(request, item=item, error=None)


@router.post("/{entry_id}")
def update_view(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    activity_type: Annotated[str, Form()],
    duration_minutes: Annotated[str, Form()],
    exercise_date: Annotated[str, Form(alias="date")],
    notes: Annotated[str, Form()] = "",
) -> Response:
    item = get_exercise_entry(db, entry_id)
    form_data = {
        "activity_type": activity_type,
        "duration_minutes": duration_minutes,
        "date": exercise_date,
        "notes": notes,
    }
    if not activity_type.strip():
        return _render_form(
            request,
            item=item,
            error="Activity type is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_duration, duration_error = _parse_duration(duration_minutes)
    if duration_error:
        return _render_form(
            request,
            item=item,
            error=duration_error,
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(exercise_date)
    if date_error:
        return _render_form(
            request,
            item=item,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    update_exercise_entry(
        db,
        entry_id=entry_id,
        activity_type=activity_type,
        duration_minutes=parsed_duration,
        entry_date=parsed_date,
        notes=notes,
    )
    return RedirectResponse(url="/exercise", status_code=303)


@router.post("/{entry_id}/delete")
def delete_view(
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    delete_exercise_entry(db, entry_id)
    return RedirectResponse(url="/exercise", status_code=303)
