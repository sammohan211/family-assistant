"""Exercise router (PRD Section 10.7).

Wires the household-shared catalog UI (`/exercise/catalog`), the per-user
body-weight setter, and the per-user exercise log (list, new, edit, delete)
at `/exercise`. The weekly aggregation view lands in the next commit.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.exercise.models import Exercise, ExerciseLog
from family_assistant.exercise.scoring import ScoringInputError
from family_assistant.exercise.services import (
    create_exercise,
    create_log,
    delete_exercise,
    delete_log,
    get_exercise,
    get_log,
    latest_log_by_exercise,
    list_exercises,
    list_user_logs,
    set_body_weight,
    update_exercise,
    update_log,
    week_start,
    weekly_summary,
)
from family_assistant.exercise.taxonomy import (
    LOCATIONS,
    MODALITIES,
    MUSCLE_GROUPS,
    REGIONS,
    muscle_label,
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
            "regions": REGIONS,
            "modalities": MODALITIES,
            "locations": LOCATIONS,
            "muscle_groups": MUSCLE_GROUPS,
            "muscle_label": muscle_label,
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


def _fmt_number(value: Decimal | int | None) -> str:
    return "" if value is None else f"{float(value):g}"


def _last_session_hint(log: ExerciseLog) -> dict[str, str]:
    """Display strings for one prior log: greyed placeholders + a summary line."""
    parts: list[str] = []
    if log.sets is not None and log.reps is not None:
        set_reps = f"{log.sets} x {log.reps}"
        if log.weight is not None:
            set_reps += f" @ {_fmt_number(log.weight)}"
        parts.append(set_reps)
    if log.distance_km is not None:
        parts.append(f"{_fmt_number(log.distance_km)} km")
    if log.duration_minutes is not None:
        parts.append(f"{log.duration_minutes} min")
    return {
        "date": f"{log.date:%b} {log.date.day}, {log.date.year}",
        "summary": " · ".join(parts),
        "score": f"{log.work_score:,.0f}",
        "sets": _fmt_number(log.sets),
        "reps": _fmt_number(log.reps),
        "weight": _fmt_number(log.weight),
        "distance_km": _fmt_number(log.distance_km),
        "duration_minutes": _fmt_number(log.duration_minutes),
    }


def _last_sessions(db: DbSession, user: User) -> dict[str, dict[str, str]]:
    return {
        str(exercise_id): _last_session_hint(log)
        for exercise_id, log in latest_log_by_exercise(db, user=user).items()
    }


def _render_log_form(
    request: Request,
    *,
    log_item: ExerciseLog | None,
    user: User,
    exercises: list[Exercise],
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
    last_sessions: dict[str, dict[str, str]] | None = None,
) -> Response:
    return templates.TemplateResponse(
        request,
        "exercise/form.html",
        {
            "log_item": log_item,
            "user": user,
            "exercises": exercises,
            "scoring_by_exercise": _scoring_by_exercise(exercises),
            "last_sessions": last_sessions or {},
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
# Weekly aggregation
# ---------------------------------------------------------------------------


def _parse_week_param(raw: str | None) -> date:
    """Snap ?week=YYYY-MM-DD to the Monday of that week. Default: today's week."""
    today = date.today()
    if not raw:
        return week_start(today)
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return week_start(today)
    return week_start(parsed)


@router.get("/weekly", response_class=HTMLResponse)
def weekly_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    week: Annotated[str | None, Query()] = None,
) -> Response:
    reference = _parse_week_param(week)
    summary = weekly_summary(db, user=user, reference=reference)
    prev_week = (summary.week_start - timedelta(days=7)).isoformat()
    next_week = (summary.week_start + timedelta(days=7)).isoformat()
    return templates.TemplateResponse(
        request,
        "exercise/weekly.html",
        {
            "summary": summary,
            "user": user,
            "muscle_label": muscle_label,
            "prev_week": prev_week,
            "next_week": next_week,
            "today_week_start": week_start(date.today()),
        },
    )


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
        {"exercises": exercises, "user": user, "muscle_label": muscle_label},
    )


@router.get("/catalog/new", response_class=HTMLResponse)
def catalog_new_form(request: Request, user: Annotated[User, Depends(require_user)]) -> Response:
    return _render_catalog_form(request, item=None, user=user, error=None)


def _save_catalog_form(
    request: Request,
    db: DbSession,
    *,
    user: User,
    item: Exercise | None,
    name: str,
    region: str,
    modality: str,
    location: str,
    primary_muscles: list[str],
    secondary_muscles: list[str],
    scoring_type: str,
    bodyweight_fraction: str,
) -> Response:
    """Shared create/update path: validate, save, or re-render with the error."""
    form_data = {
        "name": name,
        "region": region,
        "modality": modality,
        "location": location,
        "primary_muscles": primary_muscles,
        "secondary_muscles": secondary_muscles,
        "scoring_type": scoring_type,
        "bodyweight_fraction": bodyweight_fraction,
    }

    def fail(error: str | None, status_code: int = 400) -> Response:
        return _render_catalog_form(
            request,
            item=item,
            user=user,
            error=error,
            form_data=form_data,
            status_code=status_code,
        )

    cleaned_name = name.strip()
    if not cleaned_name:
        return fail("Name is required.")
    fraction, fraction_error = _parse_fraction(bodyweight_fraction)
    if fraction is None:
        return fail(fraction_error)
    fields = {
        "name": cleaned_name,
        "region": region,
        "modality": modality,
        "location": location,
        "primary_muscles": primary_muscles,
        "secondary_muscles": secondary_muscles,
        "scoring_type": scoring_type,
        "bodyweight_fraction": fraction,
    }
    try:
        if item is None:
            create_exercise(db, **fields)
        else:
            update_exercise(db, exercise_id=item.id, **fields)
    except ValueError as exc:
        return fail(f"{exc}.")
    except IntegrityError:
        db.rollback()
        return fail(f"An exercise named {cleaned_name!r} already exists.", status_code=409)
    return RedirectResponse(url="/exercise/catalog", status_code=303)


@router.post("/catalog")
def catalog_create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    name: Annotated[str, Form()],
    region: Annotated[str, Form()],
    modality: Annotated[str, Form()] = "strength",
    location: Annotated[str, Form()] = "both",
    primary_muscles: Annotated[list[str] | None, Form()] = None,
    secondary_muscles: Annotated[list[str] | None, Form()] = None,
    scoring_type: Annotated[str, Form()] = "weighted",
    bodyweight_fraction: Annotated[str, Form()] = "1.000",
) -> Response:
    return _save_catalog_form(
        request,
        db,
        user=user,
        item=None,
        name=name,
        region=region,
        modality=modality,
        location=location,
        primary_muscles=primary_muscles or [],
        secondary_muscles=secondary_muscles or [],
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )


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
    region: Annotated[str, Form()],
    modality: Annotated[str, Form()] = "strength",
    location: Annotated[str, Form()] = "both",
    primary_muscles: Annotated[list[str] | None, Form()] = None,
    secondary_muscles: Annotated[list[str] | None, Form()] = None,
    scoring_type: Annotated[str, Form()] = "weighted",
    bodyweight_fraction: Annotated[str, Form()] = "1.000",
) -> Response:
    item = get_exercise(db, exercise_id)
    if item is None:
        return RedirectResponse(url="/exercise/catalog", status_code=303)
    return _save_catalog_form(
        request,
        db,
        user=user,
        item=item,
        name=name,
        region=region,
        modality=modality,
        location=location,
        primary_muscles=primary_muscles or [],
        secondary_muscles=secondary_muscles or [],
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )


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
    return _render_log_form(
        request,
        log_item=None,
        user=user,
        exercises=exercises,
        error=None,
        last_sessions=_last_sessions(db, user),
    )


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
