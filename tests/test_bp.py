"""Blood pressure module tests: MAP/classification helpers, service CRUD +
trends, and the per-user routes."""

from datetime import date, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.bp.services import (
    classify,
    create_reading,
    list_user_readings,
    mean_arterial_pressure,
    trends,
)

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_map_formula() -> None:
    # (120 + 2*80) / 3 = 93.33
    assert mean_arterial_pressure(120, 80) == Decimal("93.33")
    # (129 + 2*92) / 3 = 104.33
    assert mean_arterial_pressure(129, 92) == Decimal("104.33")


def test_classify_thresholds() -> None:
    assert classify(115, 75)[0] == "Normal"
    assert classify(122, 78)[0] == "Elevated"
    assert classify(135, 85)[0] == "Stage 1"
    assert classify(120, 85)[0] == "Stage 1"  # diastolic drives it
    assert classify(145, 88)[0] == "Stage 2"
    assert classify(190, 80)[0] == "Hypertensive crisis"


# ---------------------------------------------------------------------------
# Service CRUD + trends
# ---------------------------------------------------------------------------


def test_create_persists_map(db_session: Session, seeded_user: User) -> None:
    reading = create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 9),
        reading_time=time(6, 30),
        systolic=129,
        diastolic=92,
        heart_rate=70,
        notes="morning",
    )
    assert reading.map_value == Decimal("104.33")
    assert list_user_readings(db_session, user=seeded_user) == [reading]


def test_trends_aggregates(db_session: Session, seeded_user: User) -> None:
    create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 11),
        reading_time=None,
        systolic=130,
        diastolic=80,
        heart_rate=70,
        notes=None,
    )
    create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 12),
        reading_time=None,
        systolic=120,
        diastolic=80,
        heart_rate=80,
        notes=None,
    )
    summary = trends(db_session, user=seeded_user)
    assert summary.count == 2
    assert summary.avg_systolic == Decimal("125.0")
    assert summary.avg_heart_rate == Decimal("75.0")
    assert summary.latest is not None and summary.latest.date == date(2024, 11, 12)
    # both fall in the same ISO week
    assert len(summary.weekly) == 1
    assert summary.weekly[0].count == 2


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_list_and_create_flow(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    assert authenticated_client.get("/bp").status_code == 200

    resp = authenticated_client.post(
        "/bp",
        data={
            "date": "2024-11-09",
            "reading_time": "06:30",
            "systolic": "129",
            "diastolic": "92",
            "heart_rate": "70",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    readings = list_user_readings(db_session, user=seeded_user)
    assert len(readings) == 1
    assert readings[0].systolic == 129

    assert authenticated_client.get("/bp/trends").status_code == 200


def test_create_rejects_diastolic_above_systolic(authenticated_client: TestClient) -> None:
    resp = authenticated_client.post(
        "/bp",
        data={"date": "2024-11-09", "systolic": "90", "diastolic": "95"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Diastolic" in resp.text


def test_delete_removes_reading(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    reading = create_reading(
        db_session,
        user=seeded_user,
        entry_date=date(2024, 11, 9),
        reading_time=None,
        systolic=120,
        diastolic=80,
        heart_rate=None,
        notes=None,
    )
    resp = authenticated_client.post(f"/bp/{reading.id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert list_user_readings(db_session, user=seeded_user) == []
