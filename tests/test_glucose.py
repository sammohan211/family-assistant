"""Blood glucose module tests: context-aware classification, service CRUD +
trends, and the owner-restricted routes (404 for anyone but the designated
owner, per PRD §10.15/§13)."""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.auth.models import User, UserSession
from family_assistant.auth.services import hash_password
from family_assistant.glucose.services import (
    classify,
    create_reading,
    list_user_readings,
    trends,
)
from family_assistant.settings import get_settings

OWNER_EMAIL = "owner@example.com"

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_classify_fasting_thresholds() -> None:
    assert classify(95, "fasting")[0] == "Normal"
    assert classify(110, "fasting")[0] == "Elevated"
    assert classify(130, "fasting")[0] == "High"


def test_classify_after_meal_and_random_share_scale() -> None:
    for context in ("after_meal", "random"):
        assert classify(120, context)[0] == "Normal"
        assert classify(160, context)[0] == "Elevated"
        assert classify(210, context)[0] == "High"


# ---------------------------------------------------------------------------
# Service CRUD + trends
# ---------------------------------------------------------------------------


def test_create_and_list(db_session: Session, seeded_user: User) -> None:
    reading = create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 9),
        reading_time=time(7, 0),
        value_mg_dl=95,
        context="fasting",
        notes="oatmeal",
    )
    assert reading.value_mg_dl == 95
    assert list_user_readings(db_session, user=seeded_user) == [reading]


def test_trends_aggregates_by_context(db_session: Session, seeded_user: User) -> None:
    create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 11),
        reading_time=None,
        value_mg_dl=95,
        context="fasting",
        notes=None,
    )
    create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 11),
        reading_time=None,
        value_mg_dl=155,
        context="after_meal",
        notes="pasta",
    )
    summary = trends(db_session, user=seeded_user)
    assert summary.count == 2
    assert summary.latest is not None and summary.latest.context == "after_meal"
    by_context = {c.context: c for c in summary.context_averages}
    assert by_context["fasting"].avg_value == 95
    assert by_context["after_meal"].avg_value == 155
    assert len(summary.weekly) == 1
    assert summary.weekly[0].count == 2
    assert len(summary.chart_points) == 2
    assert summary.chart_points[-1]["notes"] == "pasta"


# ---------------------------------------------------------------------------
# Routes: owner-only access
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_user(db_session: Session, user_password: str, monkeypatch: pytest.MonkeyPatch) -> User:
    """A user whose email matches settings.user1_email for the duration of the test."""
    monkeypatch.setenv("USER1_EMAIL", OWNER_EMAIL)
    get_settings.cache_clear()
    user = User(name="Owner", email=OWNER_EMAIL, password_hash=hash_password(user_password))
    db_session.add(user)
    db_session.commit()
    yield user
    get_settings.cache_clear()


@pytest.fixture
def owner_client(
    client: TestClient, owner_user: User, user_password: str, db_session: Session
) -> TestClient:
    client.post(
        "/auth/login",
        data={"email": owner_user.email, "password": user_password},
        follow_redirects=False,
    )
    session_row = db_session.scalar(select(UserSession).where(UserSession.user_id == owner_user.id))
    assert session_row is not None
    csrf_token = session_row.csrf_token

    original_post = client.post

    def post_with_csrf(url, *args, data=None, **kwargs):
        merged = dict(data or {})
        merged.setdefault("_csrf", csrf_token)
        return original_post(url, *args, data=merged, **kwargs)

    client.post = post_with_csrf  # type: ignore[method-assign]
    return client


def test_non_owner_gets_404(authenticated_client: TestClient, owner_user: User) -> None:
    """seeded_user (alice@example.com) is never the owner while USER1_EMAIL is patched."""
    assert authenticated_client.get("/glucose").status_code == 404
    assert authenticated_client.get("/glucose/trends").status_code == 404
    assert authenticated_client.get("/glucose/new").status_code == 404


def test_owner_list_and_create_flow(
    owner_client: TestClient, db_session: Session, owner_user: User
) -> None:
    assert owner_client.get("/glucose").status_code == 200

    resp = owner_client.post(
        "/glucose",
        data={
            "date": "2024-11-09",
            "reading_time": "07:00",
            "value_mg_dl": "95",
            "context": "fasting",
            "notes": "oatmeal",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    readings = list_user_readings(db_session, user=owner_user)
    assert len(readings) == 1
    assert readings[0].value_mg_dl == 95

    assert owner_client.get("/glucose/trends").status_code == 200


def test_create_rejects_invalid_context(owner_client: TestClient) -> None:
    resp = owner_client.post(
        "/glucose",
        data={"date": "2024-11-09", "value_mg_dl": "95", "context": "bogus"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "context" in resp.text.lower()


def test_delete_removes_reading(
    owner_client: TestClient, db_session: Session, owner_user: User
) -> None:
    reading = create_reading(
        db_session,
        user=owner_user,
        entry_date=date(2024, 11, 9),
        reading_time=None,
        value_mg_dl=100,
        context="random",
        notes=None,
    )
    resp = owner_client.post(f"/glucose/{reading.id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert list_user_readings(db_session, user=owner_user) == []
