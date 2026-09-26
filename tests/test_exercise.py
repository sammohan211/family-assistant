"""Exercise module tests (PRD §10.7 redesign).

UI routes (catalog form, log form, weekly view) land in follow-up commits;
this file covers the scoring calculator, service-layer CRUD + weekly
aggregation, and the assistant tool's name-lookup behavior.
"""

import re
from datetime import date, timedelta
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
from family_assistant.exercise.models import Exercise, ExerciseLog
from family_assistant.exercise.scoring import ScoringInputError, compute_work_score
from family_assistant.exercise.services import (
    create_exercise,
    create_log,
    get_exercise,
    get_exercise_by_name,
    latest_log_by_exercise,
    list_exercises,
    set_body_weight,
    update_log,
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


def test_scoring_timed_is_minutes() -> None:
    score = compute_work_score(
        "timed",
        body_weight=None,
        bodyweight_fraction=None,
        sets=None,
        reps=None,
        weight=None,
        distance_km=Decimal("4.9"),
        duration_minutes=195,
    )
    assert score == Decimal("195")


def test_scoring_timed_without_duration_raises() -> None:
    with pytest.raises(ScoringInputError, match="duration_minutes"):
        compute_work_score(
            "timed",
            body_weight=None,
            bodyweight_fraction=None,
            sets=None,
            reps=None,
            weight=None,
            distance_km=Decimal("5"),
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_create_exercise_normalizes_muscles(db_session: Session) -> None:
    ex = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["Triceps", "  chest  ", "chest"],
        secondary_muscles=["front_delts"],
        scoring_type="weighted",
    )
    # Deduped, lowercased, and in vocabulary order.
    assert ex.primary_muscles == ["chest", "triceps"]
    assert ex.secondary_muscles == ["front_delts"]
    assert (ex.modality, ex.location) == ("strength", "both")
    assert ex.bodyweight_fraction == Decimal("1.000")


@pytest.mark.parametrize(
    ("primary", "secondary", "message"),
    [
        (["pecs"], [], "Unknown muscle"),
        ([], ["chest"], "at least one primary"),
        (["chest"], ["chest"], "both primary and secondary"),
    ],
)
def test_create_exercise_rejects_bad_muscles(
    db_session: Session, primary: list[str], secondary: list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        create_exercise(
            db_session,
            name="Bench press",
            region="upper",
            primary_muscles=primary,
            secondary_muscles=secondary,
            scoring_type="weighted",
        )


def test_create_exercise_rejects_unknown_region(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Unknown region"):
        create_exercise(
            db_session,
            name="Bench press",
            region="torso",
            primary_muscles=["chest"],
            scoring_type="weighted",
        )


def test_get_exercise_by_name_is_case_insensitive(db_session: Session) -> None:
    create_exercise(
        db_session,
        name="Hike",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="distance",
    )
    found = get_exercise_by_name(db_session, "hike")
    assert found is not None and found.name == "Hike"


def test_list_exercises_sorted_by_name(db_session: Session) -> None:
    create_exercise(
        db_session,
        name="Squat",
        region="lower",
        primary_muscles=["quads"],
        scoring_type="weighted",
    )
    create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
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
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
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
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
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
        region="upper",
        primary_muscles=["chest"],
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


def _pushups(db: Session) -> Exercise:
    return create_exercise(
        db,
        name="Pushups",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="bodyweight_fraction",
        bodyweight_fraction=Decimal("0.5"),
    )


def test_create_log_records_body_weight_used(db_session: Session, seeded_user: User) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("180"))
    log = create_log(
        db_session,
        user=seeded_user,
        exercise=_pushups(db_session),
        entry_date=date(2026, 5, 18),
        sets=2,
        reps=10,
        weight=None,
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    assert log.body_weight_used == Decimal("180")
    assert log.work_score == Decimal("1800")  # 180 x 0.5 x 10 x 2


def test_update_log_rescores_with_original_body_weight(
    db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("180"))
    pushups = _pushups(db_session)
    log = create_log(
        db_session,
        user=seeded_user,
        exercise=pushups,
        entry_date=date(2026, 5, 18),
        sets=2,
        reps=10,
        weight=None,
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("200"))

    # Fixing a typo in an old entry must not apply today's weight.
    updated = update_log(
        db_session,
        log_id=log.id,
        user=seeded_user,
        exercise=pushups,
        entry_date=date(2026, 5, 18),
        sets=2,
        reps=12,
        weight=None,
        distance_km=None,
        duration_minutes=None,
        notes="fixed reps",
    )
    assert updated is not None
    assert updated.body_weight_used == Decimal("180")
    assert updated.work_score == Decimal("2160")  # 180 x 0.5 x 12 x 2


# ---------------------------------------------------------------------------
# Router: auth + body-weight
# ---------------------------------------------------------------------------


def test_exercise_route_requires_auth(client: TestClient) -> None:
    response = client.get("/exercise", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_log_list_empty_state(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise")
    assert response.status_code == 200
    assert b"No sessions logged yet" in response.content
    assert b"Body weight" in response.content


def test_body_weight_set_via_form(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authenticated_client.post(
        "/exercise/body-weight",
        data={"body_weight": "75.5", "redirect_to": "/exercise/catalog"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(seeded_user)
    assert seeded_user.body_weight == Decimal("75.5")


def test_body_weight_cleared_when_blank(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    response = authenticated_client.post(
        "/exercise/body-weight",
        data={"body_weight": "", "redirect_to": "/exercise/catalog"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(seeded_user)
    assert seeded_user.body_weight is None


# ---------------------------------------------------------------------------
# Catalog UI
# ---------------------------------------------------------------------------


def test_catalog_list_renders_empty_state(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise/catalog")
    assert response.status_code == 200
    assert b"No exercises yet" in response.content


def test_catalog_list_renders_existing_exercises(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="weighted",
    )
    response = authenticated_client.get("/exercise/catalog")
    assert response.status_code == 200
    assert b"Bench press" in response.content
    assert b"Chest" in response.content


def test_catalog_create_via_form(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/exercise/catalog",
        data={
            "name": "Captain's chair",
            "region": "core",
            "modality": "strength",
            "location": "gym",
            "primary_muscles": ["abs", "hip_flexors"],
            "scoring_type": "bodyweight_fraction",
            "bodyweight_fraction": "0.5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    item = get_exercise_by_name(db_session, "Captain's chair")
    assert item is not None
    assert (item.region, item.modality, item.location) == ("core", "strength", "gym")
    assert item.primary_muscles == ["abs", "hip_flexors"]
    assert item.secondary_muscles == []
    assert item.scoring_type == "bodyweight_fraction"
    assert item.bodyweight_fraction == Decimal("0.5")


def test_catalog_create_rejects_blank_name(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/exercise/catalog",
        data={
            "name": "   ",
            "region": "upper",
            "primary_muscles": ["chest"],
            "scoring_type": "weighted",
            "bodyweight_fraction": "1.000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Name is required" in response.content


def test_catalog_create_rejects_unknown_region(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/exercise/catalog",
        data={
            "name": "Bench press",
            "region": "torso",  # not in REGIONS
            "primary_muscles": ["chest"],
            "scoring_type": "weighted",
            "bodyweight_fraction": "1.000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Unknown region" in response.content


def test_catalog_create_requires_a_primary_muscle(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/exercise/catalog",
        data={
            "name": "Mystery",
            "region": "upper",
            "secondary_muscles": ["biceps"],
            "scoring_type": "weighted",
            "bodyweight_fraction": "1.000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"at least one primary muscle" in response.content
    # The re-rendered form keeps what was ticked.
    assert re.search(rb'value="biceps"\s+checked', response.content)
    assert get_exercise_by_name(db_session, "Mystery") is None


def test_catalog_create_rejects_duplicate_name(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="weighted",
    )
    response = authenticated_client.post(
        "/exercise/catalog",
        data={
            "name": "Bench press",
            "region": "upper",
            "primary_muscles": ["chest"],
            "scoring_type": "weighted",
            "bodyweight_fraction": "1.000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert b"already exists" in response.content


def test_catalog_edit_form_renders(authenticated_client: TestClient, db_session: Session) -> None:
    item = create_exercise(
        db_session,
        name="Run",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="distance",
    )
    response = authenticated_client.get(f"/exercise/catalog/{item.id}/edit")
    assert response.status_code == 200
    assert b"Run" in response.content


def test_catalog_update_via_form(authenticated_client: TestClient, db_session: Session) -> None:
    item = create_exercise(
        db_session,
        name="Squat",
        region="lower",
        primary_muscles=["quads"],
        scoring_type="weighted",
    )
    response = authenticated_client.post(
        f"/exercise/catalog/{item.id}",
        data={
            "name": "Back squat",
            "region": "lower",
            "primary_muscles": ["quads", "glutes"],
            "secondary_muscles": ["hamstrings"],
            "scoring_type": "weighted",
            "bodyweight_fraction": "1.000",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(item)
    assert item.name == "Back squat"
    assert item.primary_muscles == ["quads", "glutes"]
    assert item.secondary_muscles == ["hamstrings"]


def test_catalog_delete_via_form(authenticated_client: TestClient, db_session: Session) -> None:
    item = create_exercise(
        db_session,
        name="Yoga",
        region="core",
        primary_muscles=["abs"],
        scoring_type="weighted",
    )
    item_id = item.id
    response = authenticated_client.post(
        f"/exercise/catalog/{item_id}/delete", follow_redirects=False
    )
    assert response.status_code == 303
    assert get_exercise(db_session, item_id) is None


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
        region="upper",
        primary_muscles=["chest"],
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


# ---------------------------------------------------------------------------
# Log UI
# ---------------------------------------------------------------------------


def test_log_new_form_empty_catalog_warns(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise/new")
    assert response.status_code == 200
    assert b"No exercises in the catalog yet" in response.content


def test_log_new_form_renders_with_catalog(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="weighted",
    )
    response = authenticated_client.get("/exercise/new")
    assert response.status_code == 200
    assert b"Bench press" in response.content


def test_log_create_weighted(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    from family_assistant.exercise.services import list_user_logs

    ex = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="weighted",
    )
    response = authenticated_client.post(
        "/exercise",
        data={
            "exercise_id": str(ex.id),
            "date": "2026-05-18",
            "sets": "3",
            "reps": "10",
            "weight": "60",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    logs = list_user_logs(db_session, user=seeded_user)
    assert len(logs) == 1
    assert logs[0].work_score == Decimal("1800")


def test_log_create_distance_requires_body_weight(
    authenticated_client: TestClient, db_session: Session
) -> None:
    ex = create_exercise(
        db_session,
        name="Run",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="distance",
    )
    response = authenticated_client.post(
        "/exercise",
        data={
            "exercise_id": str(ex.id),
            "date": "2026-05-18",
            "distance_km": "5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"body_weight" in response.content


def test_log_create_distance_succeeds_with_body_weight(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    from family_assistant.exercise.services import list_user_logs

    set_body_weight(db_session, user=seeded_user, body_weight=Decimal("80"))
    ex = create_exercise(
        db_session,
        name="Run",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="distance",
    )
    response = authenticated_client.post(
        "/exercise",
        data={
            "exercise_id": str(ex.id),
            "date": "2026-05-18",
            "distance_km": "5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    logs = list_user_logs(db_session, user=seeded_user)
    assert len(logs) == 1
    assert logs[0].work_score == Decimal("400")


def test_log_create_rejects_blank_exercise(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/exercise",
        data={"exercise_id": "", "date": "2026-05-18"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Pick an exercise" in response.content


def test_log_create_rejects_bad_date(authenticated_client: TestClient, db_session: Session) -> None:
    ex = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        scoring_type="weighted",
    )
    response = authenticated_client.post(
        "/exercise",
        data={
            "exercise_id": str(ex.id),
            "date": "not-a-date",
            "sets": "3",
            "reps": "10",
            "weight": "60",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Date must be YYYY-MM-DD" in response.content


def test_log_edit_and_update(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    ex = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
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
    edit_response = authenticated_client.get(f"/exercise/{log.id}/edit")
    assert edit_response.status_code == 200
    assert b"Edit session" in edit_response.content

    update_response = authenticated_client.post(
        f"/exercise/{log.id}",
        data={
            "exercise_id": str(ex.id),
            "date": "2026-05-18",
            "sets": "4",
            "reps": "10",
            "weight": "60",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303
    db_session.refresh(log)
    assert log.sets == 4
    assert log.work_score == Decimal("2400")


def test_log_delete(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    ex = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
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
    log_id = log.id
    response = authenticated_client.post(f"/exercise/{log_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(ExerciseLog, log_id) is None


# ---------------------------------------------------------------------------
# Weekly view UI
# ---------------------------------------------------------------------------


def test_weekly_view_empty_state(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise/weekly")
    assert response.status_code == 200
    assert b"No sessions logged this week" in response.content
    assert b"Strength sets" in response.content
    assert b"never trained" in response.content


def test_weekly_view_renders_sets_minutes_and_recency(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    bench = create_exercise(
        db_session,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        secondary_muscles=["triceps"],
        scoring_type="weighted",
    )
    hike = create_exercise(
        db_session,
        name="Hiking",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="timed",
    )
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    create_log(
        db_session,
        user=seeded_user,
        exercise=bench,
        entry_date=monday,
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
        exercise=hike,
        entry_date=monday,
        sets=None,
        reps=None,
        weight=None,
        distance_km=None,
        duration_minutes=95,
        notes=None,
    )
    response = authenticated_client.get("/exercise/weekly")
    assert response.status_code == 200
    body = response.text
    assert "Week in progress" in body
    assert "Balance" in body
    assert "Push 4.5 : pull 0 sets" in body  # chest 3 + triceps 1.5
    assert "Cardio minutes" in body
    assert 'tabular-nums">95</p>' in body
    assert "Bench press" in body  # progress row
    assert "first time" in body


def test_weekly_view_accepts_week_param(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise/weekly?week=2026-05-13")
    assert response.status_code == 200
    # Page header snaps to Monday of that week.
    assert b"May 11, 2026" in response.content
    assert b"Complete week" in response.content


def test_weekly_view_bad_week_param_falls_back_to_today(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/exercise/weekly?week=not-a-date")
    assert response.status_code == 200


def test_weekly_view_shows_delta_vs_prior(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    ex = create_exercise(
        db_session,
        name="Run",
        region="full",
        modality="cardio",
        primary_muscles=["quads"],
        scoring_type="timed",
    )
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    for entry_date, minutes in [(monday - timedelta(days=7), 30), (monday, 50)]:
        create_log(
            db_session,
            user=seeded_user,
            exercise=ex,
            entry_date=entry_date,
            sets=None,
            reps=None,
            weight=None,
            distance_km=None,
            duration_minutes=minutes,
            notes=None,
        )
    response = authenticated_client.get("/exercise/weekly")
    assert response.status_code == 200
    assert b"+20 vs. last week" in response.content


# ---------------------------------------------------------------------------
# "Last time" hints on the log form
# ---------------------------------------------------------------------------


def _log_weighted(db: Session, user: User, exercise, entry_date: date, weight: str):
    return create_log(
        db,
        user=user,
        exercise=exercise,
        entry_date=entry_date,
        sets=3,
        reps=10,
        weight=Decimal(weight),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )


def test_latest_log_by_exercise_picks_most_recent_per_exercise(
    db_session: Session, seeded_user: User
) -> None:
    from family_assistant.auth.services import hash_password

    other = User(name="Bob", email="bob@example.com", password_hash=hash_password("x"))
    db_session.add(other)
    db_session.commit()
    curl = create_exercise(
        db_session, name="Curl", region="upper", primary_muscles=["chest"], scoring_type="weighted"
    )
    row = create_exercise(
        db_session, name="Row", region="upper", primary_muscles=["chest"], scoring_type="weighted"
    )
    _log_weighted(db_session, seeded_user, curl, date(2026, 9, 10), "30")
    latest_curl = _log_weighted(db_session, seeded_user, curl, date(2026, 9, 19), "36")
    _log_weighted(db_session, seeded_user, curl, date(2026, 9, 15), "33")
    latest_row = _log_weighted(db_session, seeded_user, row, date(2026, 9, 12), "80")
    _log_weighted(db_session, other, curl, date(2026, 9, 25), "50")

    latest = latest_log_by_exercise(db_session, user=seeded_user)

    assert {k: v.id for k, v in latest.items()} == {curl.id: latest_curl.id, row.id: latest_row.id}


def test_new_log_form_shows_last_session_hint(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    curl = create_exercise(
        db_session, name="Curl", region="upper", primary_muscles=["chest"], scoring_type="weighted"
    )
    _log_weighted(db_session, seeded_user, curl, date(2026, 9, 19), "36")

    response = authenticated_client.get("/exercise/new")

    assert response.status_code == 200
    body = response.text
    assert "Use last values" in body
    assert "Sep 19, 2026" in body
    assert "1,080" in body  # 36 x 10 x 3


def test_edit_log_form_has_no_last_session_hints(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    curl = create_exercise(
        db_session, name="Curl", region="upper", primary_muscles=["chest"], scoring_type="weighted"
    )
    log = _log_weighted(db_session, seeded_user, curl, date(2026, 9, 19), "36")

    response = authenticated_client.get(f"/exercise/{log.id}/edit")

    assert response.status_code == 200
    assert "Sep 19, 2026" not in response.text
