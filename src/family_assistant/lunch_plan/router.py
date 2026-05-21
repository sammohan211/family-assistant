"""School lunch planning router (PRD Section 10.6)."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.lunch_plan.models import LunchPlanEntry
from family_assistant.lunch_plan.services import (
    PACKED_STATUSES,
    create_lunch_plan_entry,
    delete_lunch_plan_entry,
    get_lunch_plan_entry,
    list_family_members,
    list_week_entries,
    set_packed_status,
    start_of_week,
    update_lunch_plan_entry,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/lunch-plan",
    tags=["lunch-plan"],
    dependencies=[Depends(require_user)],
)


def _parse_date(value: str) -> tuple[date | None, str | None]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Date must be in YYYY-MM-DD format."


def _week_days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


_WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _member_grid(
    member, member_entries: list[LunchPlanEntry], week_days: list[date]
) -> dict[str, object]:
    """Days shown per member = school_days union days with existing entries this week."""
    school_set = {d.lower() for d in (member.school_days or [])}
    days_with_entries = {entry.date for entry in member_entries}
    days = [
        day
        for day in week_days
        if _WEEKDAY_NAMES[day.weekday()] in school_set or day in days_with_entries
    ]
    entries_by_day: dict[date, list[LunchPlanEntry]] = {day: [] for day in days}
    for entry in member_entries:
        entries_by_day[entry.date].append(entry)
    return {"days": days, "entries_by_day": entries_by_day}


def _parse_items(raw_items: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in raw_items.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            name, notes = line.split(":", 1)
            item = {"name": name.strip()}
            if notes.strip():
                item["notes"] = notes.strip()
            items.append(item)
            continue
        items.append({"name": line})
    return items


def _render_items(items: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in items:
        if item.get("notes"):
            lines.append(f"{item['name']}: {item['notes']}")
        else:
            lines.append(item["name"])
    return "\n".join(lines)


def _build_member_grids(
    entries: list[LunchPlanEntry], members: list, week_days: list[date]
) -> dict[int, dict[str, object]]:
    by_member: dict[int, list[LunchPlanEntry]] = {member.id: [] for member in members}
    for entry in entries:
        by_member.setdefault(entry.family_member_id, []).append(entry)
    return {member.id: _member_grid(member, by_member[member.id], week_days) for member in members}


def _render_form(
    request: Request,
    *,
    item: LunchPlanEntry | None,
    family_members: list,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "lunch_plan/form.html",
        {
            "item": item,
            "family_members": family_members,
            "error": error,
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
    family_members = list_family_members(db)
    entries = list_week_entries(db, week_start=selected_start)
    week_days = _week_days(selected_start)
    return templates.TemplateResponse(
        request,
        "lunch_plan/list.html",
        {
            "week_start": selected_start,
            "week_end": selected_start + timedelta(days=6),
            "family_members": family_members,
            "member_grids": _build_member_grids(entries, family_members, week_days),
            "prev_week": selected_start - timedelta(days=7),
            "next_week": selected_start + timedelta(days=7),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    meal_date: Annotated[str | None, Query(alias="date")] = None,
    family_member_id: Annotated[int | None, Query()] = None,
) -> Response:
    family_members = list_family_members(db)
    prefilled_member_id = family_member_id
    if prefilled_member_id is None and len(family_members) == 1:
        prefilled_member_id = family_members[0].id
    return _render_form(
        request,
        item=None,
        family_members=family_members,
        error=None,
        form_data={
            "date": meal_date or date.today().isoformat(),
            "family_member_id": str(prefilled_member_id or ""),
        },
    )


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    family_member_id: Annotated[int, Form()],
    lunch_date: Annotated[str, Form(alias="date")],
    raw_items: Annotated[str, Form(alias="items_text")],
    notes: Annotated[str, Form()] = "",
) -> Response:
    family_members = list_family_members(db)
    form_data = {
        "family_member_id": str(family_member_id),
        "date": lunch_date,
        "items_text": raw_items,
        "notes": notes,
    }
    parsed_date, date_error = _parse_date(lunch_date)
    if date_error:
        return _render_form(
            request,
            item=None,
            family_members=family_members,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    member_ids = {member.id for member in family_members}
    if family_member_id not in member_ids:
        return _render_form(
            request,
            item=None,
            family_members=family_members,
            error="Choose a family member.",
            form_data=form_data,
            status_code=400,
        )
    items = _parse_items(raw_items)
    if not items:
        return _render_form(
            request,
            item=None,
            family_members=family_members,
            error="At least one lunch item is required.",
            form_data=form_data,
            status_code=400,
        )
    create_lunch_plan_entry(
        db,
        user=user,
        family_member_id=family_member_id,
        entry_date=parsed_date,
        items=items,
        notes=notes,
        packed_status="planned",
    )
    redirect_url = f"/lunch-plan?week_start={start_of_week(parsed_date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_lunch_plan_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/lunch-plan", status_code=303)
    family_members = list_family_members(db)
    return _render_form(
        request,
        item=item,
        family_members=family_members,
        error=None,
        form_data={"items_text": _render_items(item.items)},
    )


@router.post("/{entry_id}")
def update_view(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    family_member_id: Annotated[int, Form()],
    lunch_date: Annotated[str, Form(alias="date")],
    raw_items: Annotated[str, Form(alias="items_text")],
    notes: Annotated[str, Form()] = "",
) -> Response:
    item = get_lunch_plan_entry(db, entry_id)
    # Row deleted between GET and POST (stale tab, another device). Mirror the
    # GET edit_form behavior rather than silently no-op the update.
    if item is None:
        return RedirectResponse(url="/lunch-plan", status_code=303)
    family_members = list_family_members(db)
    form_data = {
        "family_member_id": str(family_member_id),
        "date": lunch_date,
        "items_text": raw_items,
        "notes": notes,
    }
    parsed_date, date_error = _parse_date(lunch_date)
    if date_error:
        return _render_form(
            request,
            item=item,
            family_members=family_members,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    member_ids = {member.id for member in family_members}
    if family_member_id not in member_ids:
        return _render_form(
            request,
            item=item,
            family_members=family_members,
            error="Choose a family member.",
            form_data=form_data,
            status_code=400,
        )
    items = _parse_items(raw_items)
    if not items:
        return _render_form(
            request,
            item=item,
            family_members=family_members,
            error="At least one lunch item is required.",
            form_data=form_data,
            status_code=400,
        )
    existing_status = item.packed_status if item else "planned"
    update_lunch_plan_entry(
        db,
        entry_id=entry_id,
        family_member_id=family_member_id,
        entry_date=parsed_date,
        items=items,
        notes=notes,
        packed_status=existing_status,
    )
    redirect_url = f"/lunch-plan?week_start={start_of_week(parsed_date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{entry_id}/status")
def set_status_view(
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    packed_status: Annotated[str, Form()],
) -> Response:
    if packed_status not in PACKED_STATUSES:
        return RedirectResponse(url="/lunch-plan", status_code=303)
    entry = set_packed_status(db, entry_id=entry_id, packed_status=packed_status)
    if entry is None:
        return RedirectResponse(url="/lunch-plan", status_code=303)
    redirect_url = f"/lunch-plan?week_start={start_of_week(entry.date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/{entry_id}/delete")
def delete_view(
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_lunch_plan_entry(db, entry_id)
    delete_lunch_plan_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/lunch-plan", status_code=303)
    redirect_url = f"/lunch-plan?week_start={start_of_week(item.date).isoformat()}"
    return RedirectResponse(url=redirect_url, status_code=303)
