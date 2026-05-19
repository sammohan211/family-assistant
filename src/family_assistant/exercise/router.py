"""Exercise router (PRD Section 10.7).

Wires the household-shared catalog UI (`/exercise/catalog`), the per-user
body-weight setter, and the per-user exercise log (list, new, edit, delete)
at `/exercise`. The weekly aggregation view lands in the next commit.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.exercise.models import Exercise, ExerciseLog
from family_assistant.exercise.scoring import (
    BODY_GROUPS,
    SCORING_TYPES,
    ScoringInputError,
)
from family_assistant.exercise.services import (
    create_exercise,
    create_log,
    delete_exercise,
    delete_log,
    get_exercise,
    get_log,
    list_exercises,
    list_user_logs,
    set_body_weight,
    update_exercise,
    update_log,
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
# Helpers used by the log routes
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> tuple[date | None, str | None]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None, "Date is required."
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Date must be YYYY-MM-DD."


def _parse_optional_int(raw: str, label: str) -> tuple[int | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, None
    try:
        value = int(cleaned)
    except ValueError:
        return None, f"{label} must be a whole number."
    if value < 1:
        return None, f"{label} must be 1 or greater."
    return value, None


def _parse_optional_decimal(raw: str, label: str) -> tuple[Decimal | None, str | None]:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None, None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None, f"{label} must be a decimal number."
    if value < 0:
        return None, f"{label} must be 0 or greater."
    return value, None


def _scoring_by_exercise(exercises: list[Exercise]) -> dict[str, str]:
    return {str(ex.id): ex.scoring_type for ex in exercises}


def _render_log_form(
    request: Request,
    *,
    log_item: ExerciseLog | None,
    user: User,
    exercises: list[Exercise],
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "exercise/form.html",
        {
            "log_item": log_item,
            "user": user,
            "exercises": exercises,
            "scoring_by_exercise": _scoring_by_exercise(exercises),
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# Log list (current user's history)
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def log_list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    logs = list_user_logs(db, user=user)
    return templates.TemplateResponse(
        request,
        "exercise/list.html",
        {"logs": logs, "user": user},
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


# ---------------------------------------------------------------------------
# Log (per-user; declared after catalog so /catalog/* wins literal matching,
# and after /body-weight for the same reason)
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def log_new_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    exercises = list_exercises(db)
    return _render_log_form(request, log_item=None, user=user, exercises=exercises, error=None)


def _validate_and_create_or_update(
    *,
    db: DbSession,
    log_item: ExerciseLog | None,
    user: User,
    exercises: list[Exercise],
    request: Request,
    exercise_id_raw: str,
    date_raw: str,
    sets_raw: str,
    reps_raw: str,
    weight_raw: str,
    distance_km_raw: str,
    duration_minutes_raw: str,
    notes: str,
) -> Response:
    form_data = {
        "exercise_id": exercise_id_raw,
        "date": date_raw,
        "sets": sets_raw,
        "reps": reps_raw,
        "weight": weight_raw,
        "distance_km": distance_km_raw,
        "duration_minutes": duration_minutes_raw,
        "notes": notes,
    }

    if not exercise_id_raw:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error="Pick an exercise from the catalog.",
            form_data=form_data,
            status_code=400,
        )
    try:
        exercise_id = int(exercise_id_raw)
    except ValueError:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error="Invalid exercise selection.",
            form_data=form_data,
            status_code=400,
        )
    exercise = get_exercise(db, exercise_id)
    if exercise is None:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error="Exercise no longer exists.",
            form_data=form_data,
            status_code=400,
        )

    entry_date, date_error = _parse_date(date_raw)
    if date_error is not None:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error=date_error,
            form_data=form_data,
            status_code=400,
        )
    assert entry_date is not None

    sets, sets_error = _parse_optional_int(sets_raw, "Sets")
    reps, reps_error = _parse_optional_int(reps_raw, "Reps")
    duration, duration_error = _parse_optional_int(duration_minutes_raw, "Duration")
    weight, weight_error = _parse_optional_decimal(weight_raw, "Weight")
    distance_km, distance_error = _parse_optional_decimal(distance_km_raw, "Distance")

    field_error = sets_error or reps_error or duration_error or weight_error or distance_error
    if field_error is not None:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error=field_error,
            form_data=form_data,
            status_code=400,
        )

    try:
        if log_item is None:
            create_log(
                db,
                user=user,
                exercise=exercise,
                entry_date=entry_date,
                sets=sets,
                reps=reps,
                weight=weight,
                distance_km=distance_km,
                duration_minutes=duration,
                notes=notes or None,
            )
        else:
            update_log(
                db,
                log_id=log_item.id,
                user=user,
                exercise=exercise,
                entry_date=entry_date,
                sets=sets,
                reps=reps,
                weight=weight,
                distance_km=distance_km,
                duration_minutes=duration,
                notes=notes or None,
            )
    except ScoringInputError as exc:
        return _render_log_form(
            request,
            log_item=log_item,
            user=user,
            exercises=exercises,
            error=str(exc),
            form_data=form_data,
            status_code=400,
        )

    return RedirectResponse(url="/exercise", status_code=303)


@router.post("")
def log_create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    exercise_id: Annotated[str, Form()] = "",
    date: Annotated[str, Form()] = "",
    sets: Annotated[str, Form()] = "",
    reps: Annotated[str, Form()] = "",
    weight: Annotated[str, Form()] = "",
    distance_km: Annotated[str, Form()] = "",
    duration_minutes: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    exercises = list_exercises(db)
    return _validate_and_create_or_update(
        db=db,
        log_item=None,
        user=user,
        exercises=exercises,
        request=request,
        exercise_id_raw=exercise_id,
        date_raw=date,
        sets_raw=sets,
        reps_raw=reps,
        weight_raw=weight,
        distance_km_raw=distance_km,
        duration_minutes_raw=duration_minutes,
        notes=notes,
    )


@router.get("/{log_id}/edit", response_class=HTMLResponse)
def log_edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    log_id: int,
) -> Response:
    log_item = get_log(db, log_id)
    if log_item is None or log_item.user_id != user.id:
        return RedirectResponse(url="/exercise", status_code=303)
    exercises = list_exercises(db)
    return _render_log_form(request, log_item=log_item, user=user, exercises=exercises, error=None)


@router.post("/{log_id}")
def log_update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    log_id: int,
    exercise_id: Annotated[str, Form()] = "",
    date: Annotated[str, Form()] = "",
    sets: Annotated[str, Form()] = "",
    reps: Annotated[str, Form()] = "",
    weight: Annotated[str, Form()] = "",
    distance_km: Annotated[str, Form()] = "",
    duration_minutes: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    log_item = get_log(db, log_id)
    if log_item is None or log_item.user_id != user.id:
        return RedirectResponse(url="/exercise", status_code=303)
    exercises = list_exercises(db)
    return _validate_and_create_or_update(
        db=db,
        log_item=log_item,
        user=user,
        exercises=exercises,
        request=request,
        exercise_id_raw=exercise_id,
        date_raw=date,
        sets_raw=sets,
        reps_raw=reps,
        weight_raw=weight,
        distance_km_raw=distance_km,
        duration_minutes_raw=duration_minutes,
        notes=notes,
    )


@router.post("/{log_id}/delete")
def log_delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    log_id: int,
) -> Response:
    log_item = get_log(db, log_id)
    if log_item is None or log_item.user_id != user.id:
        return RedirectResponse(url="/exercise", status_code=303)
    delete_log(db, log_id)
    return RedirectResponse(url="/exercise", status_code=303)
