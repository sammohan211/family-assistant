"""School lunch planning router (PRD Section 10.6)."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
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
from family_assistant.meal_plan.models import Recipe
from family_assistant.meal_plan.services import (
    create_recipe,
    delete_recipe,
    get_recipe,
    list_recipes,
    parse_ingredients,
    update_recipe,
)
from family_assistant.templating import templates

# School-lunch components all share meal_type="lunch" in the recipes table.
LUNCH_MEAL_TYPE = "lunch"

router = APIRouter(
    prefix="/lunch-plan",
    tags=["lunch-plan"],
    dependencies=[Depends(require_user)],
)


def _parse_optional_int(raw: str, label: str) -> tuple[int | None, str | None]:
    cleaned = raw.strip()
    if not cleaned:
        return None, None
    try:
        value = int(cleaned)
    except ValueError:
        return None, f"{label} must be a whole number."
    if value < 0:
        return None, f"{label} cannot be negative."
    return value, None


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
    db: DbSession,
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
            "lunch_recipes": list_recipes(db, meal_type=LUNCH_MEAL_TYPE),
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
        db=db,
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
            db=db,
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
            db=db,
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
            db=db,
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


# ---------------------------------------------------------------------------
# Lunch catalog (school-lunch components in the shared recipes table).
# Declared before the dynamic /{entry_id} routes so POST /catalog isn't
# captured by POST /{entry_id}.
# ---------------------------------------------------------------------------


def _render_recipe_form(
    request: Request,
    *,
    item: Recipe | None,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "lunch_plan/catalog/form.html",
        {"item": item, "error": error, "form_data": form_data or {}},
        status_code=status_code,
    )


def _recipe_form_data(
    *,
    name: str,
    ingredients: str,
    instructions: str,
    notes: str,
    calories: str,
    protein_g: str,
) -> dict[str, str]:
    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": notes,
        "calories": calories,
        "protein_g": protein_g,
    }


@router.get("/catalog", response_class=HTMLResponse)
def catalog_list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    return templates.TemplateResponse(
        request,
        "lunch_plan/catalog/list.html",
        {"recipes": list_recipes(db, meal_type=LUNCH_MEAL_TYPE)},
    )


@router.get("/catalog/new", response_class=HTMLResponse)
def catalog_new_form(request: Request) -> Response:
    return _render_recipe_form(request, item=None, error=None)


@router.post("/catalog")
def catalog_create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    ingredients: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
    protein_g: Annotated[str, Form()] = "",
) -> Response:
    form_data = _recipe_form_data(
        name=name,
        ingredients=ingredients,
        instructions=instructions,
        notes=notes,
        calories=calories,
        protein_g=protein_g,
    )
    if not name.strip():
        return _render_recipe_form(
            request,
            item=None,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    calories_val, calories_error = _parse_optional_int(calories, "Calories")
    if calories_error:
        return _render_recipe_form(
            request, item=None, error=calories_error, form_data=form_data, status_code=400
        )
    protein_val, protein_error = _parse_optional_int(protein_g, "Protein")
    if protein_error:
        return _render_recipe_form(
            request, item=None, error=protein_error, form_data=form_data, status_code=400
        )
    try:
        create_recipe(
            db,
            name=name,
            meal_type=LUNCH_MEAL_TYPE,
            ingredients=parse_ingredients(ingredients),
            instructions=instructions,
            notes=notes,
            calories=calories_val,
            protein_g=protein_val,
        )
    except IntegrityError:
        db.rollback()
        return _render_recipe_form(
            request,
            item=None,
            error=f"A recipe named {name.strip()!r} already exists.",
            form_data=form_data,
            status_code=409,
        )
    return RedirectResponse(url="/lunch-plan/catalog", status_code=303)


@router.get("/catalog/{recipe_id}/edit", response_class=HTMLResponse)
def catalog_edit_form(
    request: Request,
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_recipe(db, recipe_id)
    if item is None:
        return RedirectResponse(url="/lunch-plan/catalog", status_code=303)
    return _render_recipe_form(request, item=item, error=None)


@router.post("/catalog/{recipe_id}")
def catalog_update_view(
    request: Request,
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    ingredients: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
    protein_g: Annotated[str, Form()] = "",
) -> Response:
    item = get_recipe(db, recipe_id)
    if item is None:
        return RedirectResponse(url="/lunch-plan/catalog", status_code=303)
    form_data = _recipe_form_data(
        name=name,
        ingredients=ingredients,
        instructions=instructions,
        notes=notes,
        calories=calories,
        protein_g=protein_g,
    )
    if not name.strip():
        return _render_recipe_form(
            request,
            item=item,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    calories_val, calories_error = _parse_optional_int(calories, "Calories")
    if calories_error:
        return _render_recipe_form(
            request, item=item, error=calories_error, form_data=form_data, status_code=400
        )
    protein_val, protein_error = _parse_optional_int(protein_g, "Protein")
    if protein_error:
        return _render_recipe_form(
            request, item=item, error=protein_error, form_data=form_data, status_code=400
        )
    try:
        update_recipe(
            db,
            recipe_id=recipe_id,
            name=name,
            meal_type=LUNCH_MEAL_TYPE,
            ingredients=parse_ingredients(ingredients),
            instructions=instructions,
            notes=notes,
            calories=calories_val,
            protein_g=protein_val,
        )
    except IntegrityError:
        db.rollback()
        return _render_recipe_form(
            request,
            item=item,
            error=f"A recipe named {name.strip()!r} already exists.",
            form_data=form_data,
            status_code=409,
        )
    return RedirectResponse(url="/lunch-plan/catalog", status_code=303)


@router.post("/catalog/{recipe_id}/delete")
def catalog_delete_view(
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    delete_recipe(db, recipe_id)
    return RedirectResponse(url="/lunch-plan/catalog", status_code=303)


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
        db=db,
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
            db=db,
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
            db=db,
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
            db=db,
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
