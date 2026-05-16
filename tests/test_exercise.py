"""Exercise module integration tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.exercise.models import ExerciseEntry


def test_exercise_requires_auth(client: TestClient) -> None:
    response = client.get("/exercise", follow_redirects=False)
    assert response.status_code == 401


def test_exercise_list_renders_for_authenticated_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/exercise")
    assert response.status_code == 200
    assert b"Exercise log" in response.content
    assert b"No exercise logged yet" in response.content


def test_create_exercise_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    response = authenticated_client.post(
        "/exercise",
        data={
            "activity_type": "Cycling",
            "duration_minutes": "45",
            "date": "2026-05-18",
            "notes": "Intervals on the trainer",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    entry = db_session.scalars(select(ExerciseEntry)).one()
    assert entry.user_id == seeded_user.id
    assert entry.activity_type == "Cycling"
    assert entry.duration_minutes == 45
    assert entry.date == date(2026, 5, 18)
    assert entry.notes == "Intervals on the trainer"


def test_create_requires_activity_type(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/exercise",
        data={"activity_type": "   ", "duration_minutes": "30", "date": "2026-05-18"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Activity type is required" in response.content


def test_create_rejects_invalid_duration(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/exercise",
        data={"activity_type": "Run", "duration_minutes": "abc", "date": "2026-05-18"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Duration must be a whole number" in response.content


def test_update_exercise_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = ExerciseEntry(
        user_id=seeded_user.id,
        activity_type="Walk",
        duration_minutes=20,
        date=date(2026, 5, 18),
        notes=None,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/exercise/{entry.id}",
        data={
            "activity_type": "Walk",
            "duration_minutes": "35",
            "date": "2026-05-19",
            "notes": "Added hills",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(entry)
    assert entry.duration_minutes == 35
    assert entry.date == date(2026, 5, 19)
    assert entry.notes == "Added hills"


def test_delete_exercise_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = ExerciseEntry(
        user_id=seeded_user.id,
        activity_type="Yoga",
        duration_minutes=30,
        date=date(2026, 5, 18),
        notes=None,
    )
    db_session.add(entry)
    db_session.commit()
    entry_id = entry.id

    response = authenticated_client.post(f"/exercise/{entry_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(ExerciseEntry, entry_id) is None
