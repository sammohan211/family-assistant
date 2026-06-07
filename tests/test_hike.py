"""Hike module tests: speed helper, service CRUD + progress, and the
per-user routes."""

from datetime import date, time
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.hike.services import (
    compute_speed,
    create_hike,
    list_user_hikes,
    progress,
)

# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def test_compute_speed() -> None:
    # 12.34 km over 250 min -> 2.962 km/h
    assert compute_speed(Decimal("12.34"), 250) == Decimal("2.962")


def test_compute_speed_zero_duration() -> None:
    assert compute_speed(Decimal("5"), 0) == Decimal("0.000")


# ---------------------------------------------------------------------------
# Service CRUD + progress
# ---------------------------------------------------------------------------


def _make(db: Session, user: User, *, section: str, name: str, dist: str, mins: int, day: int):
    return create_hike(
        db,
        user=user,
        entry_date=date(2024, 8, day),
        section=section,
        name=name,
        start_location="https://maps.app.goo.gl/start",
        start_time=time(7, 45),
        end_location="https://maps.app.goo.gl/end",
        end_time=time(11, 55),
        distance_km=Decimal(dist),
        duration_minutes=mins,
        notes=None,
    )


def test_create_persists_speed(db_session: Session, seeded_user: User) -> None:
    hike = _make(
        db_session, seeded_user, section="Toronto", name="A to B", dist="12.34", mins=250, day=10
    )
    assert hike.speed_kmh == Decimal("2.962")
    assert list_user_hikes(db_session, user=seeded_user) == [hike]


def test_progress_totals_and_sections(db_session: Session, seeded_user: User) -> None:
    _make(db_session, seeded_user, section="Toronto", name="A to B", dist="10", mins=120, day=10)
    _make(db_session, seeded_user, section="Niagara", name="C to D", dist="20", mins=240, day=11)
    summary = progress(db_session, user=seeded_user)
    assert summary.count == 2
    assert summary.total_distance_km == Decimal("30")
    assert summary.total_minutes == 360
    assert summary.avg_speed_kmh == Decimal("5.000")
    # sorted by distance desc -> Niagara first
    assert [s.section for s in summary.by_section] == ["Niagara", "Toronto"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_list_and_create_flow(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    assert authenticated_client.get("/hike").status_code == 200

    resp = authenticated_client.post(
        "/hike",
        data={
            "date": "2024-08-10",
            "section": "Toronto",
            "name": "Kelso to Speyside",
            "distance_km": "12.34",
            "duration_minutes": "250",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    hikes = list_user_hikes(db_session, user=seeded_user)
    assert len(hikes) == 1 and hikes[0].name == "Kelso to Speyside"

    assert authenticated_client.get("/hike/progress").status_code == 200


def test_create_requires_section(authenticated_client: TestClient) -> None:
    resp = authenticated_client.post(
        "/hike",
        data={
            "date": "2024-08-10",
            "section": "",
            "name": "X",
            "distance_km": "5",
            "duration_minutes": "60",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Section" in resp.text


def test_delete_removes_hike(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    hike = _make(
        db_session, seeded_user, section="Toronto", name="A to B", dist="5", mins=60, day=10
    )
    resp = authenticated_client.post(f"/hike/{hike.id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert list_user_hikes(db_session, user=seeded_user) == []
