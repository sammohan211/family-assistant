"""Dashboard training priorities (PRD §10.16 step 3)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.exercise.models import Exercise, ExerciseLog, TrainingPriorities
from family_assistant.exercise.priorities import (
    CannedPrioritiesLLM,
    PrioritiesError,
    _options,
    rank_areas,
    refresh_priorities,
    validate_answer,
)
from family_assistant.exercise.router import get_priorities_llm
from family_assistant.exercise.services import create_exercise, create_log
from family_assistant.exercise.summary import build_week_summary
from family_assistant.main import app

TODAY = date(2026, 9, 30)  # a Wednesday; the week started Mon Sep 28
MON = date(2026, 9, 28)


# ---------------------------------------------------------------------------
# Pure ranking + validation
# ---------------------------------------------------------------------------


def _ex(name: str, primary: list[str], *, modality="strength", location="both", secondary=()):
    return Exercise(
        name=name,
        region="upper",
        modality=modality,
        location=location,
        primary_muscles=list(primary),
        secondary_muscles=list(secondary),
        scoring_type="timed" if modality == "cardio" else "weighted",
    )


BENCH = _ex("Bench press", ["chest"], location="gym", secondary=["triceps"])
PUSH_UP = _ex("Push-up", ["chest"], location="home", secondary=["triceps"])
ROW = _ex("Seated row", ["upper_back"], location="gym", secondary=["biceps"])
SQUAT = _ex("Goblet squat", ["quads", "glutes"])
ROWER = _ex("Rowing machine", ["upper_back"], modality="cardio", location="home")
CATALOG = [BENCH, PUSH_UP, ROW, SQUAT, ROWER]


def _log(i: int, exercise: Exercise, day: date, *, sets=3, minutes=None) -> ExerciseLog:
    return ExerciseLog(
        id=i,
        exercise=exercise,
        date=day,
        sets=None if minutes else sets,
        duration_minutes=minutes,
        work_score=Decimal(minutes or 100),
    )


def _weeks(logs: list[ExerciseLog]) -> tuple[list[dict], dict]:
    history = [
        build_week_summary(logs, start=MON - timedelta(days=7 * n), today=TODAY)
        for n in range(4, 0, -1)
    ]
    return history, build_week_summary(logs, start=MON, today=TODAY)


def _steady_logs() -> list[ExerciseLog]:
    """Four weeks of bench, row and squats, plus an hour of rowing each week."""
    logs = []
    for n in range(1, 5):
        monday = MON - timedelta(days=7 * n)
        logs += [
            _log(10 * n + 1, BENCH, monday, sets=6),
            _log(10 * n + 2, ROW, monday + timedelta(days=2), sets=6),
            _log(10 * n + 3, SQUAT, monday + timedelta(days=4), sets=6),
            _log(10 * n + 4, ROWER, monday + timedelta(days=5), minutes=60),
        ]
    return logs


def test_untrained_areas_rank_with_gym_and_home_options() -> None:
    history, current = _weeks(_steady_logs())
    areas = rank_areas(history, current, CATALOG)

    assert 2 <= len(areas) <= 3
    push = next(a for a in areas if a["area"] == "Upper push")
    assert push["muscles"][0] == "chest"
    assert push["gym"][0] == "Bench press"
    assert "Push-up" in push["home"] and "Bench press" not in push["home"]
    assert "Chest:" in push["reason"] and "sets this week" in push["reason"]


def test_never_trained_muscles_rank_below_lapsed_ones() -> None:
    history, current = _weeks(_steady_logs())
    push = next(a for a in rank_areas(history, current, CATALOG) if a["area"] == "Upper push")
    by_muscle = {m["muscle"]: m["score"] for m in push["detail"]}
    assert by_muscle["chest"] > by_muscle["front_delts"] > 0


def test_muscles_done_this_week_are_not_suggested() -> None:
    logs = [
        *_steady_logs(),
        _log(100, BENCH, MON, sets=8),  # chest covered this week; triceps got 4 at half credit
        _log(101, PUSH_UP, MON + timedelta(days=1), sets=4),
    ]
    history, current = _weeks(logs)
    suggested = {m for a in rank_areas(history, current, CATALOG) for m in a["muscles"]}
    assert "chest" not in suggested
    assert "triceps" not in suggested


def test_options_favour_the_lead_muscle_over_minor_ones() -> None:
    curl = _ex("Hammer curl", ["biceps", "forearms"], location="home")
    one_arm_row = _ex("One-arm row", ["upper_back"], location="home", secondary=["biceps"])
    need = {"upper_back": 0.9, "rear_delts": 0.7, "forearms": 0.6}

    options = _options([curl, one_arm_row, BENCH], need, "strength")

    assert options == {"gym": [], "home": ["One-arm row", "Hammer curl"]}


def test_cardio_below_usual_minutes_is_suggested() -> None:
    history, current = _weeks(_steady_logs())
    cardio = next(a for a in rank_areas(history, current, CATALOG) if a["area"] == "Cardio")
    assert cardio["home"] == ["Rowing machine"]
    assert cardio["reason"] == "0 of ~60 cardio minutes this week."


def test_validate_answer_drops_invented_names_and_areas() -> None:
    history, current = _weeks(_steady_logs())
    areas = rank_areas(history, current, CATALOG)
    raw = {
        "priorities": [
            {
                "area": "upper push",
                "muscles": ["chest", "wings"],
                "reason": "  Chest has   waited a while. ",
                "gym": ["BENCH PRESS", "Cable fly"],
                "home": ["Push-up", "Bench press"],
            },
            {"area": "Arms day", "muscles": ["biceps"], "gym": ["Seated row"]},
            {"area": "Upper push", "gym": ["Bench press"]},  # duplicate area
        ],
        "keep_it_up": "Nice work.",
    }

    valid = validate_answer(raw, areas)

    assert valid == {
        "priorities": [
            {
                "area": "Upper push",
                "muscles": ["chest"],
                "reason": "Chest has waited a while.",
                "gym": ["Bench press"],
                "home": ["Push-up"],
            }
        ],
        "keep_it_up": "Nice work.",
    }


@pytest.mark.parametrize(
    "raw",
    [
        {"priorities": [{"area": "Upper push", "gym": ["Cable fly"], "home": []}]},
        {"priorities": "chest"},
        ["not", "an", "object"],
    ],
)
def test_validate_answer_returns_none_when_nothing_usable(raw: Any) -> None:
    history, current = _weeks(_steady_logs())
    assert validate_answer(raw, rank_areas(history, current, CATALOG)) is None


# ---------------------------------------------------------------------------
# Refresh + storage (DB)
# ---------------------------------------------------------------------------


class FakeLLM:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return CannedPrioritiesLLM().chat_json(messages)


def _seed(db: Session, user: User, day: date) -> None:
    bench = create_exercise(
        db,
        name="Bench press",
        region="upper",
        primary_muscles=["chest"],
        location="gym",
        scoring_type="weighted",
    )
    create_exercise(
        db,
        name="Push-up",
        region="upper",
        primary_muscles=["chest"],
        location="home",
        scoring_type="bodyweight_fraction",
    )
    create_log(
        db,
        user=user,
        exercise=bench,
        entry_date=day,
        sets=3,
        reps=10,
        weight=Decimal("50"),
        distance_km=None,
        duration_minutes=None,
        notes=None,
    )


def test_refresh_stores_one_row_per_week_and_overwrites(
    db_session: Session, seeded_user: User
) -> None:
    _seed(db_session, seeded_user, TODAY - timedelta(days=10))
    llm = FakeLLM()

    first = refresh_priorities(db_session, user=seeded_user, llm=llm, model_label="m", today=TODAY)
    refresh_priorities(db_session, user=seeded_user, llm=llm, model_label="m", today=TODAY)

    rows = db_session.scalars(select(TrainingPriorities)).all()
    assert len(rows) == 1 and rows[0].id == first.id
    assert llm.calls == 2
    assert rows[0].week_start == MON
    assert rows[0].is_fallback is False and rows[0].model == "m"
    names = [p["area"] for p in rows[0].content["priorities"]]
    assert "Upper push" in names
    push = next(p for p in rows[0].content["priorities"] if p["area"] == "Upper push")
    assert push["gym"] == ["Bench press"] and push["home"] == ["Push-up"]


def test_llm_failure_falls_back_to_the_ranking(db_session: Session, seeded_user: User) -> None:
    _seed(db_session, seeded_user, TODAY - timedelta(days=10))

    row = refresh_priorities(
        db_session, user=seeded_user, llm=FakeLLM(fail=True), model_label="m", today=TODAY
    )

    assert row.is_fallback is True and row.model is None
    push = next(p for p in row.content["priorities"] if p["area"] == "Upper push")
    assert push["reason"].startswith("Chest: last trained 10 days ago")


def test_refresh_needs_recent_logs(db_session: Session, seeded_user: User) -> None:
    _seed(db_session, seeded_user, TODAY - timedelta(days=40))
    with pytest.raises(PrioritiesError):
        refresh_priorities(
            db_session, user=seeded_user, llm=FakeLLM(), model_label="m", today=TODAY
        )


# ---------------------------------------------------------------------------
# Dashboard card
# ---------------------------------------------------------------------------


def test_card_hidden_without_recent_logs(authenticated_client: TestClient) -> None:
    body = authenticated_client.get("/dashboard").text
    assert "Training this week" not in body


def test_card_refresh_flow(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    _seed(db_session, seeded_user, date.today() - timedelta(days=10))
    llm = FakeLLM()
    app.dependency_overrides[get_priorities_llm] = lambda: llm
    try:
        before = authenticated_client.get("/dashboard").text
        assert "Training this week" in before
        assert "Press Refresh" in before

        response = authenticated_client.post("/exercise/priorities/refresh", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard#training"

        after = authenticated_client.get("/dashboard").text
        assert "Upper push" in after
        assert "Gym:</span> Bench press" in after
        assert "Home:</span> Push-up" in after
        assert llm.calls == 1
    finally:
        app.dependency_overrides.pop(get_priorities_llm, None)
