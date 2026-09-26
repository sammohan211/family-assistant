"""Exercise CRUD + weekly aggregation services (PRD Section 10.7).

Exposes:
  - Catalog CRUD on the household-shared ``Exercise`` table.
  - Per-user log CRUD on ``ExerciseLog``, computing and persisting
    ``work_score`` on every create/update via :mod:`exercise.scoring`.
  - ``set_body_weight`` for the per-user body weight on the User profile.
  - Invalidation of stored weekly summaries (:mod:`exercise.summary`) whenever
    a log or catalog entry changes.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.exercise.models import Exercise, ExerciseLog
from family_assistant.exercise.scoring import SCORING_TYPES, compute_work_score
from family_assistant.exercise.summary import invalidate_all, invalidate_weeks
from family_assistant.exercise.taxonomy import LOCATIONS, MODALITIES, MUSCLES, REGIONS

# ---------------------------------------------------------------------------
# Catalog (household-shared)
# ---------------------------------------------------------------------------


def list_exercises(db: DbSession) -> list[Exercise]:
    return list(db.scalars(select(Exercise).order_by(Exercise.name.asc())).all())


def get_exercise(db: DbSession, exercise_id: int) -> Exercise | None:
    return db.get(Exercise, exercise_id)


def get_exercise_by_name(db: DbSession, name: str) -> Exercise | None:
    cleaned = name.strip()
    if not cleaned:
        return None
    statement = select(Exercise).where(Exercise.name.ilike(cleaned))
    return db.scalars(statement).first()


def _normalize_muscles(muscles: list[str] | tuple[str, ...]) -> list[str]:
    """Dedupe, keep vocabulary order, and reject anything outside MUSCLES."""
    cleaned = {m.strip().lower() for m in muscles if m.strip()}
    unknown = sorted(cleaned - set(MUSCLES))
    if unknown:
        raise ValueError(f"Unknown muscle(s): {', '.join(unknown)}")
    return [m for m in MUSCLES if m in cleaned]


def _validated_catalog_fields(
    *,
    region: str,
    modality: str,
    location: str,
    primary_muscles: list[str] | tuple[str, ...],
    secondary_muscles: list[str] | tuple[str, ...],
    scoring_type: str,
    bodyweight_fraction: Decimal,
) -> tuple[list[str], list[str]]:
    """Validate catalog fields; return the normalized (primary, secondary) muscles."""
    if region not in REGIONS:
        raise ValueError(f"Unknown region: {region!r}")
    if modality not in MODALITIES:
        raise ValueError(f"Unknown modality: {modality!r}")
    if location not in LOCATIONS:
        raise ValueError(f"Unknown location: {location!r}")
    if scoring_type not in SCORING_TYPES:
        raise ValueError(f"Unknown scoring_type: {scoring_type!r}")
    if bodyweight_fraction < 0:
        raise ValueError("bodyweight_fraction must be >= 0")
    primary = _normalize_muscles(primary_muscles)
    secondary = _normalize_muscles(secondary_muscles)
    if not primary:
        raise ValueError("Pick at least one primary muscle")
    overlap = set(primary) & set(secondary)
    if overlap:
        both = ", ".join(sorted(overlap))
        raise ValueError(f"A muscle can't be both primary and secondary: {both}")
    return primary, secondary


def create_exercise(
    db: DbSession,
    *,
    name: str,
    region: str,
    primary_muscles: list[str] | tuple[str, ...],
    secondary_muscles: list[str] | tuple[str, ...] = (),
    modality: str = "strength",
    location: str = "both",
    scoring_type: str,
    bodyweight_fraction: Decimal = Decimal("1.000"),
) -> Exercise:
    primary, secondary = _validated_catalog_fields(
        region=region,
        modality=modality,
        location=location,
        primary_muscles=primary_muscles,
        secondary_muscles=secondary_muscles,
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )
    exercise = Exercise(
        name=name.strip(),
        region=region,
        modality=modality,
        location=location,
        primary_muscles=primary,
        secondary_muscles=secondary,
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


def update_exercise(
    db: DbSession,
    *,
    exercise_id: int,
    name: str,
    region: str,
    primary_muscles: list[str] | tuple[str, ...],
    secondary_muscles: list[str] | tuple[str, ...],
    modality: str,
    location: str,
    scoring_type: str,
    bodyweight_fraction: Decimal,
) -> Exercise | None:
    primary, secondary = _validated_catalog_fields(
        region=region,
        modality=modality,
        location=location,
        primary_muscles=primary_muscles,
        secondary_muscles=secondary_muscles,
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return None
    exercise.name = name.strip()
    exercise.region = region
    exercise.modality = modality
    exercise.location = location
    exercise.primary_muscles = primary
    exercise.secondary_muscles = secondary
    exercise.scoring_type = scoring_type
    exercise.bodyweight_fraction = bodyweight_fraction
    invalidate_all(db)
    db.commit()
    db.refresh(exercise)
    return exercise


def delete_exercise(db: DbSession, exercise_id: int) -> bool:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return False
    db.delete(exercise)
    invalidate_all(db)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# User body weight
# ---------------------------------------------------------------------------


def set_body_weight(db: DbSession, *, user: User, body_weight: Decimal | None) -> User:
    user.body_weight = body_weight
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Log (per-user)
# ---------------------------------------------------------------------------


def _with_relationships(statement):
    return statement.options(selectinload(ExerciseLog.exercise))


def list_user_logs(db: DbSession, *, user: User, limit: int = 100) -> list[ExerciseLog]:
    statement = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user.id)
        .order_by(
            ExerciseLog.date.desc(),
            ExerciseLog.created_at.desc(),
            ExerciseLog.id.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(_with_relationships(statement)).all())


def latest_log_by_exercise(db: DbSession, *, user: User) -> dict[int, ExerciseLog]:
    """The user's most recent log for each exercise, keyed by exercise id.

    Feeds the "last time" hints on the log form. Same tie-break order as
    ``list_user_logs`` so "most recent" means the same thing everywhere.
    """
    statement = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user.id)
        .order_by(
            ExerciseLog.exercise_id,
            ExerciseLog.date.desc(),
            ExerciseLog.created_at.desc(),
            ExerciseLog.id.desc(),
        )
        .distinct(ExerciseLog.exercise_id)
    )
    return {log.exercise_id: log for log in db.scalars(statement).all()}


def get_log(db: DbSession, log_id: int) -> ExerciseLog | None:
    statement = select(ExerciseLog).where(ExerciseLog.id == log_id)
    return db.scalars(_with_relationships(statement)).first()


def _score_for(
    *,
    exercise: Exercise,
    body_weight: Decimal | None,
    sets: int | None,
    reps: int | None,
    weight: Decimal | None,
    distance_km: Decimal | None,
    duration_minutes: int | None,
) -> Decimal:
    return compute_work_score(
        exercise.scoring_type,
        body_weight=body_weight,
        bodyweight_fraction=exercise.bodyweight_fraction,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
    )


def create_log(
    db: DbSession,
    *,
    user: User,
    exercise: Exercise,
    entry_date: date,
    sets: int | None,
    reps: int | None,
    weight: Decimal | None,
    distance_km: Decimal | None,
    duration_minutes: int | None,
    notes: str | None,
) -> ExerciseLog:
    work_score = _score_for(
        exercise=exercise,
        body_weight=user.body_weight,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
    )
    log = ExerciseLog(
        user_id=user.id,
        exercise_id=exercise.id,
        date=entry_date,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        work_score=work_score,
        body_weight_used=user.body_weight,
        notes=notes.strip() if notes else None,
    )
    db.add(log)
    invalidate_weeks(db, user_id=user.id, dates=[entry_date])
    db.commit()
    db.refresh(log)
    return log


def update_log(
    db: DbSession,
    *,
    log_id: int,
    user: User,
    exercise: Exercise,
    entry_date: date,
    sets: int | None,
    reps: int | None,
    weight: Decimal | None,
    distance_km: Decimal | None,
    duration_minutes: int | None,
    notes: str | None,
) -> ExerciseLog | None:
    log = db.get(ExerciseLog, log_id)
    if log is None:
        return None
    # Re-score with the weight the log was first scored with, so editing an old
    # entry doesn't silently apply today's body weight (PRD §10.16).
    body_weight = log.body_weight_used if log.body_weight_used is not None else user.body_weight
    work_score = _score_for(
        exercise=exercise,
        body_weight=body_weight,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
    )
    invalidate_weeks(db, user_id=log.user_id, dates=[log.date, entry_date])
    log.exercise_id = exercise.id
    log.date = entry_date
    log.sets = sets
    log.reps = reps
    log.weight = weight
    log.distance_km = distance_km
    log.duration_minutes = duration_minutes
    log.notes = notes.strip() if notes else None
    log.work_score = work_score
    log.body_weight_used = body_weight
    db.commit()
    db.refresh(log)
    return log


def delete_log(db: DbSession, log_id: int) -> bool:
    log = db.get(ExerciseLog, log_id)
    if log is None:
        return False
    invalidate_weeks(db, user_id=log.user_id, dates=[log.date])
    db.delete(log)
    db.commit()
    return True
