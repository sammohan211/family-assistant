"""Meal planning router (PRD Section 10.5)."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.meal_plan.models import MealPlanEntry
from family_assistant.meal_plan.services import (
    MEAL_TYPES,
    create_meal_plan_entry,
    delete_meal_plan_entry,
    duplicate_meal_plan_entry,
    get_meal_plan_entry,
    list_recent_entries,
    list_week_entries,
    start_of_week,
    update_meal_plan_entry,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/meal-plan",
    tags=["meal-plan"],
    dependencies=[Depends(require_user)],
)


def _parse_date(value: str) -> tuple[date | None, str | None]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Date must be in YYYY-MM-DD format."


def _validate_meal_type(value: str) -> str | None:
    if value not in MEAL_TYPES:
        return "Meal type is required."
    return None


def _week_days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


def _group_entries(
    entries: list[MealPlanEntry], week_start: date
) -> dict[date, dict[str, list[MealPlanEntry]]]:
    grouped = {day: {meal_type: [] for meal_type in MEAL_TYPES} for day in _week_days(week_start)}
    for entry in entries:
        grouped[entry.date][entry.meal_type].append(entry)
    return grouped


def _render_form(
    request: Request,
    *,
    item: MealPlanEntry | None,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "meal_plan/form.html",
        {
            "item": item,
            "error": error,
            "meal_types": MEAL_TYPES,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    week_start: Annotated[str | None, Query()] = None,
) -> Response:
    selected_start = start_of_week(date.today())
    if week_start:
        parsed, _ = _parse_date(week_start)
        if parsed is not None:
            selected_start = start_of_week(parsed)
    entries = list_week_entries(db, week_start=selected_start)
    return templates.TemplateResponse(
        request,
        "meal_plan/list.html",
        {
            "week_start": selected_start,
            "week_end": selected_start + timedelta(days=6),
            "days": _week_days(selected_start),
            "grouped_entries": _group_entries(entries, selected_start),
            "meal_types": MEAL_TYPES,
            "recent_entries": list_recent_entries(db, limit=8),
            "favorite_entries": list_recent_entries(db, limit=8, favorites_only=True),
            "prev_week": selected_start - timedelta(days=7),
            "next_week": selected_start + timedelta(days=7),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    meal_date: Annotated[str | None, Query()] = None,
    meal_type: Annotated[str | None, Query()] = None,
) -> Response:
    default_date = meal_date or date.today().isoformat()
    default_meal_type = meal_type if meal_type in MEAL_TYPES else "dinner"
    return _render_form(
        request,
        item=None,
        error=None,
        form_data={"date": default_date, "meal_type": default_meal_type},
    )


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    meal_date: Annotated[str, Form(alias="date")],
    meal_type: Annotated[str, Form()],
    title: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    is_favorite: Annotated[bool, Form()] = False,
) -> Response:
    form_data = {
        "date": meal_date,
        "meal_type": meal_type,
        "title": title,
        "notes": notes,
        "is_favorite": "on" if is_favorite else "",
    }
    if not title.strip():
        return _render_form(
            request,
            item=None,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(meal_date)
    if date_error:
        return _render_form(
            request,
            item=None,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    meal_type_error = _validate_meal_type(meal_type)
    if meal_type_error:
        return _render_form(
            request,
            item=None,
            error=meal_type_error,
            form_data=form_data,
            status_code=400,
        )
    create_meal_plan_entry(
        db,
        user=user,
        entry_date=parsed_date,
        meal_type=meal_type,
        title=title,
        notes=notes,
        is_favorite=is_favorite,
    )
    redirect_url = f"/meal-plan?week_start={start_of_week(parsed_date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_meal_plan_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/meal-plan", status_code=303)
    return _render_form(request, item=item, error=None)


@router.post("/{entry_id}")
def update_view(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    meal_date: Annotated[str, Form(alias="date")],
    meal_type: Annotated[str, Form()],
    title: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    is_favorite: Annotated[bool, Form()] = False,
) -> Response:
    item = get_meal_plan_entry(db, entry_id)
    form_data = {
        "date": meal_date,
        "meal_type": meal_type,
        "title": title,
        "notes": notes,
        "is_favorite": "on" if is_favorite else "",
    }
    if not title.strip():
        return _render_form(
            request,
            item=item,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(meal_date)
    if date_error:
        return _render_form(
            request,
            item=item,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    meal_type_error = _validate_meal_type(meal_type)
    if meal_type_error:
        return _render_form(
            request,
            item=item,
            error=meal_type_error,
            form_data=form_data,
            status_code=400,
        )
    update_meal_plan_entry(
        db,
        entry_id=entry_id,
        entry_date=parsed_date,
        meal_type=meal_type,
        title=title,
        notes=notes,
        is_favorite=is_favorite,
    )
    redirect_url = f"/meal-plan?week_start={start_of_week(parsed_date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{entry_id}/duplicate")
def duplicate_view(
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    entry_date: Annotated[str, Form(alias="date")],
) -> Response:
    parsed_date, date_error = _parse_date(entry_date)
    if date_error:
        return PlainTextResponse(date_error, status_code=400)
    duplicate_meal_plan_entry(db, entry_id=entry_id, user=user, entry_date=parsed_date)
    redirect_url = f"/meal-plan?week_start={start_of_week(parsed_date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{entry_id}/delete")
def delete_view(
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_meal_plan_entry(db, entry_id)
    delete_meal_plan_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/meal-plan", status_code=303)
    redirect_url = f"/meal-plan?week_start={start_of_week(item.date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)
