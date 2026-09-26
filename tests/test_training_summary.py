"""Weekly training summaries (PRD §10.16 step 2)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.exercise.models import Exercise, ExerciseLog, TrainingWeekSummary
from family_assistant.exercise.services import (
    create_exercise,
    create_log,
    delete_log,
    update_exercise,
    update_log,
)
from family_assistant.exercise.summary import (
    SUMMARY_VERSION,
    build_week_summary,
    get_week_summary,
)

MON = date(2026, 9, 14)  # a Monday; the week runs to Sun Sep 20
AFTER = date(2026, 9, 26)  # "today" once that week is complete


# ---------------------------------------------------------------------------
# Pure builder (no DB)
# ---------------------------------------------------------------------------


def _ex(name: str, modality: str, primary: list[str], secondary: list[str] = ()) -> Exercise:
    return Exercise(
        name=name,
        region="upper",
        modality=modality,
        location="both",
        primary_muscles=list(primary),
        secondary_muscles=list(secondary),
        scoring_type="timed" if modality == "cardio" else "weighted",
    )


def _log(log_id: int, exercise: Exercise, day: date, *, sets=None, score="0", minutes=None):
    return ExerciseLog(
        id=log_id,
        exercise=exercise,
        date=day,
        sets=sets,
        work_score=Decimal(score),
        duration_minutes=minutes,
    )


BENCH = _ex("Bench", "strength", ["chest"], ["triceps", "front_delts"])
ROW = _ex("Row", "strength", ["upper_back"], ["biceps"])
HIKE = _ex("Hiking", "cardio", ["quads", "glutes"])


def test_sets_credit_primary_in_full_and_secondary_at_half() -> None:
    logs = [_log(1, BENCH, date(2026, 9, 15), sets=3), _log(2, BENCH, date(2026, 9, 17), sets=2)]
    s = build_week_summary(logs, start=MON, today=AFTER)
    assert s["strength_sets"]["chest"] == 5
    assert s["strength_sets"]["triceps"] == 2.5
    assert s["strength_sets"]["upper_back"] == 0
    assert s["strength_sets_total"] == 5
    assert s["group_sets"] == {"Upper push": 10, "Upper pull": 0, "Core": 0, "Lower": 0}
    assert (s["active_days"], s["sessions"]) == (2, 2)


def test_cardio_counts_minutes_and_recency_but_no_sets() -> None:
    logs = [_log(1, HIKE, date(2026, 9, 19), minutes=120), _log(2, HIKE, date(2026, 9, 20))]
    s = build_week_summary(logs, start=MON, today=AFTER)
    assert s["cardio_minutes"] == {"total": 120, "by_exercise": {"Hiking": 120}}
    assert s["strength_sets"]["quads"] == 0
    assert s["days_since_trained"]["quads"] == 0  # hiked on Sunday, the week's end
    assert s["strength_sets_total"] == 0


def test_days_since_trained_as_of_week_end_and_uses_history() -> None:
    logs = [
        _log(1, ROW, date(2026, 9, 1), sets=3),  # before the week
        _log(2, BENCH, date(2026, 9, 16), sets=3),
        _log(3, BENCH, date(2026, 9, 25), sets=3),  # after the week: ignored
    ]
    s = build_week_summary(logs, start=MON, today=AFTER)
    assert s["complete"] is True
    assert s["as_of"] == "2026-09-20"
    assert s["days_since_trained"]["chest"] == 4
    assert s["days_since_trained"]["biceps"] == 19  # secondary counts for recency
    assert s["days_since_trained"]["hamstrings"] is None


def test_partial_week_is_measured_as_of_today() -> None:
    s = build_week_summary([_log(1, BENCH, MON, sets=3)], start=MON, today=date(2026, 9, 17))
    assert s["complete"] is False
    assert s["as_of"] == "2026-09-17"
    assert s["days_since_trained"]["chest"] == 3


def test_progress_compares_best_this_week_with_last_session_before() -> None:
    logs = [
        _log(1, BENCH, date(2026, 9, 3), sets=3, score="900"),
        _log(2, BENCH, date(2026, 9, 10), sets=3, score="1000"),
        _log(3, BENCH, date(2026, 9, 15), sets=3, score="1080"),
        _log(4, BENCH, date(2026, 9, 17), sets=2, score="720"),
        _log(5, ROW, date(2026, 9, 16), sets=3, score="500"),
    ]
    s = build_week_summary(logs, start=MON, today=AFTER)
    assert s["progress"] == [
        {"exercise": "Bench", "best": 1080, "previous": 1000, "change_pct": 8.0},
        {"exercise": "Row", "best": 500, "previous": None, "change_pct": None},
    ]


# ---------------------------------------------------------------------------
# Storage + invalidation (DB)
# ---------------------------------------------------------------------------


def _bench(db: Session) -> Exercise:
    return create_exercise(
        db, name="Bench", region="upper", primary_muscles=["chest"], scoring_type="weighted"
    )


def _add(db: Session, user: User, exercise: Exercise, day: date) -> ExerciseLog:
    return create_log(
        db,
        user=user,
        exercise=exercise,
        entry_date=day,
        sets=3,
        reps=10,
        weight=Decimal("50"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )


def _stored_weeks(db: Session, user: User) -> list[date]:
    return sorted(
        db.scalars(
            select(TrainingWeekSummary.week_start).where(TrainingWeekSummary.user_id == user.id)
        ).all()
    )


def test_completed_week_is_stored_and_current_week_is_not(
    db_session: Session, seeded_user: User
) -> None:
    _add(db_session, seeded_user, _bench(db_session), date(2026, 9, 15))

    done = get_week_summary(db_session, user=seeded_user, start=MON, today=AFTER)
    live = get_week_summary(db_session, user=seeded_user, start=date(2026, 9, 21), today=AFTER)

    assert done["strength_sets"]["chest"] == 3
    assert live["complete"] is False
    assert _stored_weeks(db_session, seeded_user) == [MON]


def test_log_change_drops_its_week_and_later_weeks_only(
    db_session: Session, seeded_user: User
) -> None:
    bench = _bench(db_session)
    _add(db_session, seeded_user, bench, date(2026, 9, 1))
    today = date(2026, 10, 5)
    for start in (date(2026, 8, 31), date(2026, 9, 7), MON):
        get_week_summary(db_session, user=seeded_user, start=start, today=today)
    assert len(_stored_weeks(db_session, seeded_user)) == 3

    log = _add(db_session, seeded_user, bench, date(2026, 9, 9))
    assert _stored_weeks(db_session, seeded_user) == [date(2026, 8, 31)]

    # Rebuilt on the next read, with the new log.
    rebuilt = get_week_summary(db_session, user=seeded_user, start=date(2026, 9, 7), today=today)
    assert rebuilt["strength_sets"]["chest"] == 3

    # Moving a log back to an earlier week invalidates from the earlier of the two dates.
    update_log(
        db_session,
        log_id=log.id,
        user=seeded_user,
        exercise=bench,
        entry_date=date(2026, 8, 31),
        sets=3,
        reps=10,
        weight=Decimal("50"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    assert _stored_weeks(db_session, seeded_user) == []

    get_week_summary(db_session, user=seeded_user, start=MON, today=today)
    delete_log(db_session, log.id)
    assert _stored_weeks(db_session, seeded_user) == []


def test_catalog_change_drops_every_stored_week(db_session: Session, seeded_user: User) -> None:
    bench = _bench(db_session)
    _add(db_session, seeded_user, bench, date(2026, 9, 15))
    get_week_summary(db_session, user=seeded_user, start=MON, today=AFTER)

    update_exercise(
        db_session,
        exercise_id=bench.id,
        name="Bench",
        region="upper",
        primary_muscles=["chest"],
        secondary_muscles=["triceps"],
        modality="strength",
        location="gym",
        scoring_type="weighted",
        bodyweight_fraction=Decimal("1"),
    )

    assert _stored_weeks(db_session, seeded_user) == []
    rebuilt = get_week_summary(db_session, user=seeded_user, start=MON, today=AFTER)
    assert rebuilt["strength_sets"]["triceps"] == 1.5


def test_outdated_summary_version_is_rebuilt(db_session: Session, seeded_user: User) -> None:
    _add(db_session, seeded_user, _bench(db_session), date(2026, 9, 15))
    db_session.add(TrainingWeekSummary(user_id=seeded_user.id, week_start=MON, data={"version": 0}))
    db_session.commit()

    data = get_week_summary(db_session, user=seeded_user, start=MON, today=AFTER)

    assert data["version"] == SUMMARY_VERSION
    stored = db_session.scalars(select(TrainingWeekSummary)).one()
    assert stored.data["version"] == SUMMARY_VERSION
