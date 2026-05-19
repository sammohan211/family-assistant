"""Exercise router (PRD Section 10.7).

This commit wires the household-shared catalog UI (`/exercise/catalog`) and
the per-user body-weight setter. The per-user log list and weekly view land
in subsequent commits; `/exercise` itself remains a placeholder for now.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.exercise.models import Exercise
from family_assistant.exercise.scoring import BODY_GROUPS, SCORING_TYPES
from family_assistant.exercise.services import (
    create_exercise,
    delete_exercise,
    get_exercise,
    list_exercises,
    set_body_weight,
    update_exercise,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/exercise",
    tags=["exercise"],
    dependencies=[Depends(require_user)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_tags(raw: str) -> list[str]:
    return [tag for tag in (part.strip() for part in raw.split(",")) if tag]


def _parse_fraction(raw: str) -> tuple[Decimal | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return Decimal("1.000"), None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None, "Bodyweight fraction must be a decimal number."
    if value < 0:
        return None, "Bodyweight fraction must be 0 or greater."
    return value, None


def _parse_body_weight(raw: str) -> tuple[Decimal | None, str | None, bool]:
    """Returns (value, error, cleared). cleared=True means user blanked the field."""
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, None, True
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None, "Body weight must be a decimal number.", False
    if value <= 0:
        return None, "Body weight must be greater than zero.", False
    return value, None, False


def _render_catalog_form(
    request: Request,
    *,
    item: Exercise | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "exercise/catalog/form.html",
        {
            "item": item,
            "user": user,
            "body_groups": BODY_GROUPS,
            "scoring_types": SCORING_TYPES,
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# Placeholder (replaced by the log list in commit 3)
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def placeholder(request: Request, user: Annotated[User, Depends(require_user)]) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "exercise/placeholder.html",
        {"user": user},
    )


# ---------------------------------------------------------------------------
# Body weight (per-user)
# ---------------------------------------------------------------------------


@router.post("/body-weight")
def update_body_weight(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    body_weight: Annotated[str, Form()] = "",
    redirect_to: Annotated[str, Form()] = "/exercise/catalog",
) -> Response:
    value, error, cleared = _parse_body_weight(body_weight)
    if error is not None:
        # Bounce back to wherever the user was — keep the UX simple.
        return RedirectResponse(url=redirect_to, status_code=303)
    set_body_weight(db, user=user, body_weight=None if cleared else value)
    return RedirectResponse(url=redirect_to, status_code=303)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@router.get("/catalog", response_class=HTMLResponse)
def catalog_list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    exercises = list_exercises(db)
    return templates.TemplateResponse(
        request,
        "exercise/catalog/list.html",
        {"exercises": exercises, "user": user},
    )


@router.get("/catalog/new", response_class=HTMLResponse)
def catalog_new_form(request: Request, user: Annotated[User, Depends(require_user)]) -> Response:
    return _render_catalog_form(request, item=None, user=user, error=None)


@router.post("/catalog")
def catalog_create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    name: Annotated[str, Form()],
    body_group: Annotated[str, Form()],
    muscle_groups: Annotated[str, Form()] = "",
    scoring_type: Annotated[str, Form()] = "weighted",
    bodyweight_fraction: Annotated[str, Form()] = "1.000",
) -> Response:
    form_data = {
        "name": name,
        "body_group": body_group,
        "muscle_groups": muscle_groups,
        "scoring_type": scoring_type,
        "bodyweight_fraction": bodyweight_fraction,
    }
    cleaned_name = name.strip()
    if not cleaned_name:
        return _render_catalog_form(
            request,
            item=None,
            user=user,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    if body_group not in BODY_GROUPS:
        return _render_catalog_form(
            request,
            item=None,
            user=user,
            error=f"Body group must be one of {', '.join(BODY_GROUPS)}.",
            form_data=form_data,
            status_code=400,
        )
    if scoring_type not in SCORING_TYPES:
        return _render_catalog_form(
            request,
            item=None,
            user=user,
            error=f"Scoring type must be one of {', '.join(SCORING_TYPES)}.",
            form_data=form_data,
            status_code=400,
        )
    fraction, fraction_error = _parse_fraction(bodyweight_fraction)
    if fraction is None:
        return _render_catalog_form(
            request,
            item=None,
            user=user,
            error=fraction_error,
            form_data=form_data,
            status_code=400,
        )
    try:
        create_exercise(
            db,
            name=cleaned_name,
            body_group=body_group,
            muscle_groups=_parse_tags(muscle_groups),
            scoring_type=scoring_type,
            bodyweight_fraction=fraction,
        )
    except IntegrityError:
        db.rollback()
        return _render_catalog_form(
            request,
            item=None,
            user=user,
            error=f"An exercise named {cleaned_name!r} already exists.",
            form_data=form_data,
            status_code=409,
        )
    return RedirectResponse(url="/exercise/catalog", status_code=303)


@router.get("/catalog/{exercise_id}/edit", response_class=HTMLResponse)
def catalog_edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    exercise_id: int,
) -> Response:
    item = get_exercise(db, exercise_id)
    if item is None:
        return RedirectResponse(url="/exercise/catalog", status_code=303)
    return _render_catalog_form(request, item=item, user=user, error=None)


@router.post("/catalog/{exercise_id}")
def catalog_update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    exercise_id: int,
    name: Annotated[str, Form()],
    body_group: Annotated[str, Form()],
    muscle_groups: Annotated[str, Form()] = "",
    scoring_type: Annotated[str, Form()] = "weighted",
    bodyweight_fraction: Annotated[str, Form()] = "1.000",
) -> Response:
    item = get_exercise(db, exercise_id)
    if item is None:
        return RedirectResponse(url="/exercise/catalog", status_code=303)
    form_data = {
        "name": name,
        "body_group": body_group,
        "muscle_groups": muscle_groups,
        "scoring_type": scoring_type,
        "bodyweight_fraction": bodyweight_fraction,
    }
    cleaned_name = name.strip()
    if not cleaned_name:
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    if body_group not in BODY_GROUPS:
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error=f"Body group must be one of {', '.join(BODY_GROUPS)}.",
            form_data=form_data,
            status_code=400,
        )
    if scoring_type not in SCORING_TYPES:
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error=f"Scoring type must be one of {', '.join(SCORING_TYPES)}.",
            form_data=form_data,
            status_code=400,
        )
    fraction, fraction_error = _parse_fraction(bodyweight_fraction)
    if fraction is None:
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error=fraction_error,
            form_data=form_data,
            status_code=400,
        )
    try:
        update_exercise(
            db,
            exercise_id=exercise_id,
            name=cleaned_name,
            body_group=body_group,
            muscle_groups=_parse_tags(muscle_groups),
            scoring_type=scoring_type,
            bodyweight_fraction=fraction,
        )
    except IntegrityError:
        db.rollback()
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error=f"An exercise named {cleaned_name!r} already exists.",
            form_data=form_data,
            status_code=409,
        )
    return RedirectResponse(url="/exercise/catalog", status_code=303)


@router.post("/catalog/{exercise_id}/delete")
def catalog_delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    exercise_id: int,
) -> Response:
    delete_exercise(db, exercise_id)
    return RedirectResponse(url="/exercise/catalog", status_code=303)
