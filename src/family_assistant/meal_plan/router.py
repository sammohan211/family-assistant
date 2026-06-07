"""Meal planning router (PRD Section 10.5)."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.meal_plan.models import MealPlanEntry, Recipe
from family_assistant.meal_plan.services import (
    MEAL_TYPES,
    create_meal_plan_entry,
    create_recipe,
    delete_meal_plan_entry,
    delete_recipe,
    duplicate_meal_plan_entry,
    get_meal_plan_entry,
    get_recipe,
    list_meal_recipes,
    list_recent_entries,
    list_week_entries,
    parse_ingredients,
    start_of_week,
    update_meal_plan_entry,
    update_recipe,
)
from family_assistant.templating import templates

# Meal catalog covers everything except school-lunch components (those live in
# the lunch catalog under /lunch-plan/catalog). This household only uses dinner,
# but breakfast/snack are available too.
MEAL_CATALOG_TYPES = ("dinner", "breakfast", "snack")

router = APIRouter(
    prefix="/meal-plan",
    tags=["meal-plan"],
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
    db: DbSession,
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
            "recipes": list_meal_recipes(db),
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
    db: Annotated[DbSession, Depends(get_session)],
    meal_date: Annotated[str | None, Query()] = None,
    meal_type: Annotated[str | None, Query()] = None,
) -> Response:
    default_date = meal_date or date.today().isoformat()
    default_meal_type = meal_type if meal_type in MEAL_TYPES else "dinner"
    return _render_form(
        request,
        db=db,
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
            db=db,
            item=None,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(meal_date)
    if date_error:
        return _render_form(
            request,
            db=db,
            item=None,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    meal_type_error = _validate_meal_type(meal_type)
    if meal_type_error:
        return _render_form(
            request,
            db=db,
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


# ---------------------------------------------------------------------------
# Meal catalog (household-shared recipes). Declared before the dynamic
# /{entry_id} routes so POST /catalog isn't captured by POST /{entry_id}.
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
        "meal_plan/catalog/form.html",
        {
            "item": item,
            "error": error,
            "meal_types": MEAL_CATALOG_TYPES,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


def _recipe_form_data(
    *,
    name: str,
    meal_type: str,
    ingredients: str,
    instructions: str,
    notes: str,
    calories: str,
    protein_g: str,
) -> dict[str, str]:
    return {
        "name": name,
        "meal_type": meal_type,
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": notes,
        "calories": calories,
        "protein_g": protein_g,
    }


def _validate_recipe(
    *, name: str, meal_type: str, calories: str, protein_g: str
) -> tuple[int | None, int | None, str | None]:
    if not name.strip():
        return None, None, "Name is required."
    if meal_type not in MEAL_CATALOG_TYPES:
        return None, None, f"Meal type must be one of {', '.join(MEAL_CATALOG_TYPES)}."
    calories_val, calories_error = _parse_optional_int(calories, "Calories")
    if calories_error:
        return None, None, calories_error
    protein_val, protein_error = _parse_optional_int(protein_g, "Protein")
    if protein_error:
        return None, None, protein_error
    return calories_val, protein_val, None


@router.get("/catalog", response_class=HTMLResponse)
def catalog_list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    return templates.TemplateResponse(
        request,
        "meal_plan/catalog/list.html",
        {"recipes": list_meal_recipes(db)},
    )


@router.get("/catalog/new", response_class=HTMLResponse)
def catalog_new_form(request: Request) -> Response:
    return _render_recipe_form(request, item=None, error=None, form_data={"meal_type": "dinner"})


@router.post("/catalog")
def catalog_create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    meal_type: Annotated[str, Form()] = "dinner",
    ingredients: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
    protein_g: Annotated[str, Form()] = "",
) -> Response:
    form_data = _recipe_form_data(
        name=name,
        meal_type=meal_type,
        ingredients=ingredients,
        instructions=instructions,
        notes=notes,
        calories=calories,
        protein_g=protein_g,
    )
    calories_val, protein_val, error = _validate_recipe(
        name=name, meal_type=meal_type, calories=calories, protein_g=protein_g
    )
    if error:
        return _render_recipe_form(
            request, item=None, error=error, form_data=form_data, status_code=400
        )
    try:
        create_recipe(
            db,
            name=name,
            meal_type=meal_type,
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
    return RedirectResponse(url="/meal-plan/catalog", status_code=303)


@router.get("/catalog/{recipe_id}/edit", response_class=HTMLResponse)
def catalog_edit_form(
    request: Request,
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_recipe(db, recipe_id)
    if item is None:
        return RedirectResponse(url="/meal-plan/catalog", status_code=303)
    return _render_recipe_form(request, item=item, error=None)


@router.post("/catalog/{recipe_id}")
def catalog_update_view(
    request: Request,
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    meal_type: Annotated[str, Form()] = "dinner",
    ingredients: Annotated[str, Form()] = "",
    instructions: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
    protein_g: Annotated[str, Form()] = "",
) -> Response:
    item = get_recipe(db, recipe_id)
    if item is None:
        return RedirectResponse(url="/meal-plan/catalog", status_code=303)
    form_data = _recipe_form_data(
        name=name,
        meal_type=meal_type,
        ingredients=ingredients,
        instructions=instructions,
        notes=notes,
        calories=calories,
        protein_g=protein_g,
    )
    calories_val, protein_val, error = _validate_recipe(
        name=name, meal_type=meal_type, calories=calories, protein_g=protein_g
    )
    if error:
        return _render_recipe_form(
            request, item=item, error=error, form_data=form_data, status_code=400
        )
    try:
        update_recipe(
            db,
            recipe_id=recipe_id,
            name=name,
            meal_type=meal_type,
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
    return RedirectResponse(url="/meal-plan/catalog", status_code=303)


@router.post("/catalog/{recipe_id}/delete")
def catalog_delete_view(
    recipe_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    delete_recipe(db, recipe_id)
    return RedirectResponse(url="/meal-plan/catalog", status_code=303)


@router.get("/{entry_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    entry_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_meal_plan_entry(db, entry_id)
    if item is None:
        return RedirectResponse(url="/meal-plan", status_code=303)
    return _render_form(request, db=db, item=item, error=None)


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
    # Row deleted between GET and POST (stale tab, another device). Mirror the
    # GET edit_form behavior rather than silently no-op the update.
    if item is None:
        return RedirectResponse(url="/meal-plan", status_code=303)
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
            db=db,
            item=item,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_date, date_error = _parse_date(meal_date)
    if date_error:
        return _render_form(
            request,
            db=db,
            item=item,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    meal_type_error = _validate_meal_type(meal_type)
    if meal_type_error:
        return _render_form(
            request,
            db=db,
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
