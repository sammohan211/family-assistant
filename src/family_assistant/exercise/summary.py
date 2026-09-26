"""Weekly training state summaries (PRD §10.16 step 2).

One summary per (user, ISO week), built from the exercise log with measures
that are comparable across exercises — never summed ``work_score``:

- strength sets per muscle: primary muscles 1 x logged sets, secondary 0.5 x
- sets per muscle group (push / pull / core / lower) for balance
- cardio minutes, total and per exercise
- days since each muscle was last trained, as of the week's end (strength and
  cardio both count; cardio adds no sets)
- per-exercise best ``work_score`` vs the last session before the week

Completed weeks are stored in ``training_week_summaries`` on first request and
deleted whenever a log in that week or any catalog entry changes. The current
week is always built live and marked partial.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.exercise.models import ExerciseLog, TrainingWeekSummary
from family_assistant.exercise.taxonomy import (
    MUSCLE_GROUPS,
    MUSCLES,
    PRIMARY_CREDIT,
    SECONDARY_CREDIT,
)

# Bump when the shape or meaning of the summary changes; stored summaries with an
# older version are rebuilt on read.
SUMMARY_VERSION = 1


def week_start(reference: date) -> date:
    """Monday of the ISO week containing ``reference``."""
    return reference - timedelta(days=reference.weekday())


def _num(value: Decimal) -> float | int:
    """JSON-friendly number: whole values as int, halves etc. as float."""
    return int(value) if value == value.to_integral_value() else float(value)


def _logged_sets(log: ExerciseLog) -> int:
    # Strength logs without a set count (e.g. a timed plank) count as one set.
    return log.sets if log.sets else 1


def build_week_summary(logs: list[ExerciseLog], *, start: date, today: date) -> dict[str, Any]:
    """Summarize the week starting ``start`` from the user's logs.

    ``logs`` must include every log dated before the week's end (earlier logs
    feed "days since trained" and "vs previous"). Pure: no DB access.
    """
    end = start + timedelta(days=7)
    complete = end <= today
    as_of = end - timedelta(days=1) if complete else today

    week_logs = [log for log in logs if start <= log.date < end]
    history = [log for log in logs if log.date < end]

    sets: dict[str, Decimal] = {m: Decimal("0") for m in MUSCLES}
    strength_sets = 0
    cardio_by_exercise: dict[str, int] = {}
    for log in week_logs:
        exercise = log.exercise
        if exercise.modality == "cardio":
            minutes = log.duration_minutes or 0
            cardio_by_exercise[exercise.name] = cardio_by_exercise.get(exercise.name, 0) + minutes
            continue
        n = _logged_sets(log)
        strength_sets += n
        for muscle in exercise.primary_muscles:
            sets[muscle] += PRIMARY_CREDIT * n
        for muscle in exercise.secondary_muscles:
            sets[muscle] += SECONDARY_CREDIT * n

    last_trained: dict[str, date] = {}
    for log in history:
        if log.date > as_of:
            continue
        exercise = log.exercise
        muscles = list(exercise.primary_muscles)
        if exercise.modality == "strength":
            muscles += exercise.secondary_muscles
        for muscle in muscles:
            if muscle not in last_trained or log.date > last_trained[muscle]:
                last_trained[muscle] = log.date

    progress = []
    for name in sorted({log.exercise.name for log in week_logs}):
        best = max(log.work_score for log in week_logs if log.exercise.name == name)
        before = [log for log in history if log.exercise.name == name and log.date < start]
        previous = max(before, key=lambda log: (log.date, log.id)).work_score if before else None
        change_pct = round(float((best - previous) / previous * 100), 1) if previous else None
        progress.append(
            {
                "exercise": name,
                "best": _num(best),
                "previous": _num(previous) if previous is not None else None,
                "change_pct": change_pct,
            }
        )

    return {
        "version": SUMMARY_VERSION,
        "week_start": start.isoformat(),
        "complete": complete,
        "as_of": as_of.isoformat(),
        "active_days": len({log.date for log in week_logs}),
        "sessions": len(week_logs),
        "strength_sets_total": strength_sets,
        "strength_sets": {m: _num(v) for m, v in sets.items()},
        "group_sets": {
            group: _num(sum((sets[m] for m in muscles), Decimal("0")))
            for group, muscles in MUSCLE_GROUPS.items()
        },
        "cardio_minutes": {
            "total": sum(cardio_by_exercise.values()),
            "by_exercise": dict(sorted(cardio_by_exercise.items())),
        },
        "days_since_trained": {
            m: (as_of - last_trained[m]).days if m in last_trained else None for m in MUSCLES
        },
        "progress": progress,
    }


def _logs_until(db: DbSession, *, user: User, end_exclusive: date) -> list[ExerciseLog]:
    statement = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user.id, ExerciseLog.date < end_exclusive)
        .options(selectinload(ExerciseLog.exercise))
    )
    return list(db.scalars(statement).all())


def get_week_summary(
    db: DbSession, *, user: User, start: date, today: date | None = None
) -> dict[str, Any]:
    """The summary for the week starting ``start`` (a Monday).

    Completed weeks are read from the store, or built and stored on first use;
    the current week (or a future one) is built live and never stored.
    """
    today = today or date.today()
    start = week_start(start)
    complete = start + timedelta(days=7) <= today
    if complete:
        stored = db.scalars(
            select(TrainingWeekSummary).where(
                TrainingWeekSummary.user_id == user.id,
                TrainingWeekSummary.week_start == start,
            )
        ).first()
        if stored is not None and stored.data.get("version") == SUMMARY_VERSION:
            return stored.data
        if stored is not None:
            db.delete(stored)
            db.flush()

    logs = _logs_until(db, user=user, end_exclusive=start + timedelta(days=7))
    data = build_week_summary(logs, start=start, today=today)
    if complete:
        db.add(TrainingWeekSummary(user_id=user.id, week_start=start, data=data))
        db.commit()
    return data


def invalidate_weeks(db: DbSession, *, user_id: int, dates: list[date]) -> None:
    """Drop stored summaries a log change affects: the log's week and every
    later week, whose "days since trained" and "vs previous" can depend on it.
    The caller commits."""
    earliest = min(week_start(d) for d in dates)
    db.execute(
        delete(TrainingWeekSummary).where(
            TrainingWeekSummary.user_id == user_id,
            TrainingWeekSummary.week_start >= earliest,
        )
    )


def invalidate_all(db: DbSession) -> None:
    """Drop every stored summary (a catalog change re-interprets all weeks).
    The caller commits."""
    db.execute(delete(TrainingWeekSummary))
