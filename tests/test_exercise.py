"""Exercise module tests (PRD §10.7 redesign).

UI routes (catalog form, log form, weekly view) land in follow-up commits;
this file covers the scoring calculator, service-layer CRUD + weekly
aggregation, and the assistant tool's name-lookup behavior.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.ai_gateway.tools import (
    ExerciseLogActivityArgs,
    ValidatedToolCall,
    execute_tool_call,
)
from family_assistant.auth.models import User
from family_assistant.exercise.models import ExerciseLog
from family_assistant.exercise.scoring import ScoringInputError, compute_work_score
from family_assistant.exercise.services import (
    create_exercise,
    create_log,
    get_exercise_by_name,
    list_exercises,
    set_body_weight,
    update_log,
    weekly_summary,
)

# ---------------------------------------------------------------------------
# Scoring calculator (pure)
# ---------------------------------------------------------------------------


def test_scoring_weighted_multiplies_weight_reps_sets() -> None:
    score = compute_work_score(
        "weighted",
        body_weight=None,
        bodyweight_fraction=None,
        sets=3,
        reps=10,
        weight=Decimal("60"),
        distance_km=None,
    )
    assert score == Decimal("1800")


def test_scoring_distance_uses_body_weight() -> None:
    score = compute_work_score(
        "distance",
        body_weight=Decimal("80"),
        bodyweight_fraction=None,
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("5"),
    )
    assert score == Decimal("400")


def test_scoring_bodyweight_fraction_uses_fraction_and_body_weight() -> None:
    score = compute_work_score(
        "bodyweight_fraction",
        body_weight=Decimal("80"),
        bodyweight_fraction=Decimal("0.5"),
        sets=3,
        reps=12,
        weight=None,
        distance_km=None,
    )
    assert score == Decimal("80") * Decimal("0.5") * Decimal("12") * Decimal("3")


def test_scoring_weighted_missing_inputs_raises() -> None:
    with pytest.raises(ScoringInputError):
        compute_work_score(
            "weighted",
            body_weight=None,
            bodyweight_fraction=None,
            sets=3,
            reps=10,
            weight=None,
            distance_km=None,
        )


def test_scoring_distance_without_body_weight_raises() -> None:
    with pytest.raises(ScoringInputError):
        compute_work_score(
            "distance",
            body_weight=None,
            bodyweight_fraction=None,
            sets=None,
            reps=None,
            weight=None,
            distance_km=Decimal("5"),
        )


def test_scoring_unknown_type_raises() -> None:
    with pytest.raises(ScoringInputError):
        compute_work_score(
            "isometric",
            body_weight=Decimal("80"),
            bodyweight_fraction=Decimal("1"),
            sets=1,
            reps=1,
            weight=None,
            distance_km=None,
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_create_exercise_normalizes_tags(db_session: Session) -> None:
    ex = create_exercise(
        db_session,
        name="Bench press",
        body_group="upper",
        muscle_groups=["Chest", "  chest  ", "triceps"],
        scoring_type="weighted",
    )
    assert ex.muscle_groups == ["chest", "triceps"]
    assert ex.bodyweight_fraction == Decimal("1.000")


def test_get_exercise_by_name_is_case_insensitive(db_session: Session) -> None:
    create_exercise(
        db_session,
        name="Hike",
        body_group="cardio",
        muscle_groups=[],
        scoring_type="distance",
    )
    found = get_exercise_by_name(db_session, "hike")
    assert found is not None and found.name == "Hike"


def test_list_exercises_sorted_by_name(db_session: Session) -> None:
    create_exercise(
        db_session,
        name="Squat",
        body_group="lower",
        muscle_groups=["quads"],
        scoring_type="weighted",
    )
    create_exercise(
        db_session,
        name="Bench press",
        body_group="upper",
        muscle_groups=["chest"],
        scoring_type="weighted",
    )
    names = [e.name for e in list_exercises(db_session)]
    assert names == ["Bench press", "Squat"]


# ---------------------------------------------------------------------------
# Log + persisted work_score
# ---------------------------------------------------------------------------


def test_create_log_persists_work_score(db_session: Session, seeded_user: User) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Run",
        body_group="cardio",
        muscle_groups=["legs"],
        scoring_type="distance",
    )
    log = create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("5"),
        duration_minutes=30,
        notes=None,
    )
    assert log.work_score == Decimal("400")


def test_log_score_persists_when_body_weight_later_changes(
    db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Walk",
        body_group="cardio",
        muscle_groups=[],
        scoring_type="distance",
    )
    log = create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("4"),
        duration_minutes=None,
        notes=None,
    )
    original_score = log.work_score
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("90"))
    db_session.refresh(log)
    assert log.work_score == original_score


def test_update_log_recomputes_score(db_session: Session, seeded_user: User) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Bench press",
        body_group="upper",
        muscle_groups=["chest"],
        scoring_type="weighted",
    )
    log = create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=3,
        reps=10,
        weight=Decimal("60"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    updated = update_log(
        db_session,
        log_id=log.id,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=4,
        reps=10,
        weight=Decimal("60"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    assert updated is not None
    assert updated.work_score == Decimal("2400")


# ---------------------------------------------------------------------------
# Weekly aggregation
# ---------------------------------------------------------------------------


def test_weekly_summary_groups_by_body_group_and_muscle_group(
    db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    bench = create_exercise(
        db_session,
        name="Bench press",
        body_group="upper",
        muscle_groups=["chest", "triceps"],
        scoring_type="weighted",
    )
    squat = create_exercise(
        db_session,
        name="Squat",
        body_group="lower",
        muscle_groups=["quads"],
        scoring_type="weighted",
    )
    create_log(
        db_session,
        user=seeded_user,
        exercise=bench,
        entry_date=date(2026, 5, 18),  # a Monday
        sets=3,
        reps=10,
        weight=Decimal("60"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    create_log(
        db_session,
        user=seeded_user,
        exercise=squat,
        entry_date=date(2026, 5, 20),
        sets=3,
        reps=10,
        weight=Decimal("80"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )

    summary = weekly_summary(db_session, user=seeded_user, reference=date(2026, 5, 22))
    assert summary.week_start == date(2026, 5, 18)
    assert summary.total == Decimal("1800") + Decimal("2400")
    body_scores = {row.label: row.score for row in summary.by_body_group}
    assert body_scores["upper"] == Decimal("1800")
    assert body_scores["lower"] == Decimal("2400")
    assert body_scores["core"] == Decimal("0")
    muscle_scores = {row.label: row.score for row in summary.by_muscle_group}
    assert muscle_scores["chest"] == Decimal("1800")
    assert muscle_scores["triceps"] == Decimal("1800")
    assert muscle_scores["quads"] == Decimal("2400")


def test_weekly_summary_computes_delta_vs_prior_week(
    db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Run",
        body_group="cardio",
        muscle_groups=["legs"],
        scoring_type="distance",
    )
    # Prior week (Mon May 11): 4 km -> 320
    create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 11),
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("4"),
        duration_minutes=None,
        notes=None,
    )
    # This week (Mon May 18): 5 km -> 400
    create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("5"),
        duration_minutes=None,
        notes=None,
    )
    summary = weekly_summary(db_session, user=seeded_user, reference=date(2026, 5, 18))
    assert summary.total == Decimal("400")
    assert summary.prior_total == Decimal("320")
    assert summary.delta == Decimal("80")
    assert summary.delta_pct is not None
    assert summary.delta_pct == (Decimal("80") / Decimal("320")) * Decimal("100")


def test_weekly_summary_delta_pct_none_when_no_prior(
    db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Run",
        body_group="cardio",
        muscle_groups=["legs"],
        scoring_type="distance",
    )
    create_log(
        db_session,
        user=seeded_user,
        exercise=ex,
        entry_date=date(2026, 5, 18),
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("5"),
        duration_minutes=None,
        notes=None,
    )
    summary = weekly_summary(db_session, user=seeded_user, reference=date(2026, 5, 18))
    assert summary.prior_total == Decimal("0")
    assert summary.delta_pct is None


# ---------------------------------------------------------------------------
# Router placeholder
# ---------------------------------------------------------------------------


def test_exercise_route_requires_auth(client: TestClient) -> None:
    response = client.get("/exercise", follow_redirects=False)
    assert response.status_code == 401


def test_exercise_placeholder_renders(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise")
    assert response.status_code == 200
    assert b"being rebuilt" in response.content


# ---------------------------------------------------------------------------
# Assistant tool
# ---------------------------------------------------------------------------


def test_assistant_tool_unknown_exercise_returns_not_found(
    db_session: Session, seeded_user: User
) -> None:
    args = ExerciseLogActivityArgs(
        exercise_name="Nonexistent",
        date=date(2026, 5, 18),
        sets=3,
        reps=10,
        weight=60,
    )
    result = execute_tool_call(
        ValidatedToolCall(
            name="exercise.log_activity",
            args=args,
            raw_args=args.model_dump(mode="json"),
        ),
        db_session,
        seeded_user,
    )
    assert result.outcome == "not_found"
    assert "Nonexistent" in (result.error or "")


def test_assistant_tool_logs_against_catalog(db_session: Session, seeded_user: User) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    create_exercise(
        db_session,
        name="Bench press",
        body_group="upper",
        muscle_groups=["chest"],
        scoring_type="weighted",
    )
    args = ExerciseLogActivityArgs(
        exercise_name="bench press",  # case-insensitive
        date=date(2026, 5, 18),
        sets=3,
        reps=10,
        weight=60.0,
    )
    result = execute_tool_call(
        ValidatedToolCall(
            name="exercise.log_activity",
            args=args,
            raw_args=args.model_dump(mode="json"),
        ),
        db_session,
        seeded_user,
    )
    assert result.outcome == "success"
    assert result.affected_table == "exercise_logs"
    log = db_session.get(ExerciseLog, result.affected_ids[0])
    assert log is not None
    assert log.work_score == Decimal("1800")
