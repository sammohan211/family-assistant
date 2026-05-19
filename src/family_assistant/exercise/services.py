"""Exercise CRUD + weekly aggregation services (PRD Section 10.7).

Exposes:
  - Catalog CRUD on the household-shared ``Exercise`` table.
  - Per-user log CRUD on ``ExerciseLog``, computing and persisting
    ``work_score`` on every create/update via :mod:`exercise.scoring`.
  - ``set_body_weight`` for the per-user body weight on the User profile.
  - ``weekly_summary`` aggregating one ISO week of logs with per-body-group
    and per-muscle-group totals plus delta vs. the previous week.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.exercise.models import Exercise, ExerciseLog
from family_assistant.exercise.scoring import (
    BODY_GROUPS,
    SCORING_TYPES,
    compute_work_score,
)

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


def _normalize_tags(tags: list[str]) -> list[str]:
    seen: list[str] = []
    for raw in tags:
        cleaned = raw.strip().lower()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _validate_catalog_fields(
    *,
    body_group: str,
    scoring_type: str,
    bodyweight_fraction: Decimal,
) -> None:
    if body_group not in BODY_GROUPS:
        raise ValueError(f"Unknown body_group: {body_group!r}")
    if scoring_type not in SCORING_TYPES:
        raise ValueError(f"Unknown scoring_type: {scoring_type!r}")
    if bodyweight_fraction < 0:
        raise ValueError("bodyweight_fraction must be >= 0")


def create_exercise(
    db: DbSession,
    *,
    name: str,
    body_group: str,
    muscle_groups: list[str],
    scoring_type: str,
    bodyweight_fraction: Decimal = Decimal("1.000"),
) -> Exercise:
    _validate_catalog_fields(
        body_group=body_group,
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )
    exercise = Exercise(
        name=name.strip(),
        body_group=body_group,
        muscle_groups=_normalize_tags(muscle_groups),
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
    body_group: str,
    muscle_groups: list[str],
    scoring_type: str,
    bodyweight_fraction: Decimal,
) -> Exercise | None:
    _validate_catalog_fields(
        body_group=body_group,
        scoring_type=scoring_type,
        bodyweight_fraction=bodyweight_fraction,
    )
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return None
    exercise.name = name.strip()
    exercise.body_group = body_group
    exercise.muscle_groups = _normalize_tags(muscle_groups)
    exercise.scoring_type = scoring_type
    exercise.bodyweight_fraction = bodyweight_fraction
    db.commit()
    db.refresh(exercise)
    return exercise


def delete_exercise(db: DbSession, exercise_id: int) -> bool:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        return False
    db.delete(exercise)
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


def get_log(db: DbSession, log_id: int) -> ExerciseLog | None:
    statement = select(ExerciseLog).where(ExerciseLog.id == log_id)
    return db.scalars(_with_relationships(statement)).first()


def _score_for(
    *,
    exercise: Exercise,
    user: User,
    sets: int | None,
    reps: int | None,
    weight: Decimal | None,
    distance_km: Decimal | None,
) -> Decimal:
    return compute_work_score(
        exercise.scoring_type,
        body_weight=user.body_weight,
        bodyweight_fraction=exercise.bodyweight_fraction,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
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
        user=user,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
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
        notes=notes.strip() if notes else None,
    )
    db.add(log)
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
    log.exercise_id = exercise.id
    log.date = entry_date
    log.sets = sets
    log.reps = reps
    log.weight = weight
    log.distance_km = distance_km
    log.duration_minutes = duration_minutes
    log.notes = notes.strip() if notes else None
    log.work_score = _score_for(
        exercise=exercise,
        user=user,
        sets=sets,
        reps=reps,
        weight=weight,
        distance_km=distance_km,
    )
    db.commit()
    db.refresh(log)
    return log


def delete_log(db: DbSession, log_id: int) -> bool:
    log = db.get(ExerciseLog, log_id)
    if log is None:
        return False
    db.delete(log)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Weekly aggregation
# ---------------------------------------------------------------------------


def week_start(reference: date) -> date:
    """Monday of the ISO week containing ``reference``."""
    return reference - timedelta(days=reference.weekday())


@dataclass
class WeeklyGroupTotal:
    label: str
    score: Decimal


@dataclass
class WeeklySummary:
    user_id: int
    week_start: date
    total: Decimal
    prior_total: Decimal
    delta: Decimal
    delta_pct: Decimal | None  # None when prior_total == 0
    by_body_group: list[WeeklyGroupTotal]
    by_muscle_group: list[WeeklyGroupTotal]


def _logs_in_range(
    db: DbSession, *, user: User, start: date, end_exclusive: date
) -> list[ExerciseLog]:
    statement = (
        select(ExerciseLog)
        .where(
            ExerciseLog.user_id == user.id,
            ExerciseLog.date >= start,
            ExerciseLog.date < end_exclusive,
        )
        .options(selectinload(ExerciseLog.exercise))
    )
    return list(db.scalars(statement).all())


def _total(logs: list[ExerciseLog]) -> Decimal:
    return sum((log.work_score for log in logs), Decimal("0"))


def _group_by_body_group(logs: list[ExerciseLog]) -> list[WeeklyGroupTotal]:
    totals: dict[str, Decimal] = {bg: Decimal("0") for bg in BODY_GROUPS}
    for log in logs:
        totals[log.exercise.body_group] = (
            totals.get(log.exercise.body_group, Decimal("0")) + log.work_score
        )
    return [WeeklyGroupTotal(label=bg, score=totals.get(bg, Decimal("0"))) for bg in BODY_GROUPS]


def _group_by_muscle_group(logs: list[ExerciseLog]) -> list[WeeklyGroupTotal]:
    totals: dict[str, Decimal] = {}
    for log in logs:
        for tag in log.exercise.muscle_groups or []:
            totals[tag] = totals.get(tag, Decimal("0")) + log.work_score
    return [
        WeeklyGroupTotal(label=label, score=score)
        for label, score in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]


def weekly_summary(db: DbSession, *, user: User, reference: date) -> WeeklySummary:
    start = week_start(reference)
    end = start + timedelta(days=7)
    prior_start = start - timedelta(days=7)

    this_week = _logs_in_range(db, user=user, start=start, end_exclusive=end)
    last_week = _logs_in_range(db, user=user, start=prior_start, end_exclusive=start)

    total = _total(this_week)
    prior_total = _total(last_week)
    delta = total - prior_total
    delta_pct: Decimal | None = None if prior_total == 0 else (delta / prior_total) * Decimal("100")

    return WeeklySummary(
        user_id=user.id,
        week_start=start,
        total=total,
        prior_total=prior_total,
        delta=delta,
        delta_pct=delta_pct,
        by_body_group=_group_by_body_group(this_week),
        by_muscle_group=_group_by_muscle_group(this_week),
    )
