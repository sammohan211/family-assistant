"""Household task module tests: recurrence helper, service CRUD + completion,
and the shared routes."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.household_task.services import (
    advance_due_date,
    complete_task,
    create_task,
    get_task,
    list_active_tasks,
    list_recent_completions,
)

# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def test_advance_due_date() -> None:
    assert advance_due_date(date(2026, 6, 7), "day", 3) == date(2026, 6, 10)
    assert advance_due_date(date(2026, 6, 7), "week", 1) == date(2026, 6, 14)
    assert advance_due_date(date(2026, 6, 7), "week", 2) == date(2026, 6, 21)
    assert advance_due_date(date(2026, 6, 7), "month", 1) == date(2026, 7, 7)
    # Day clamps when the target month is shorter.
    assert advance_due_date(date(2026, 1, 31), "month", 1) == date(2026, 2, 28)


# ---------------------------------------------------------------------------
# Service CRUD + completion
# ---------------------------------------------------------------------------


def test_complete_recurring_reschedules(db_session: Session, seeded_user: User) -> None:
    task = create_task(
        db_session,
        name="Laundry",
        details=None,
        assignee_id=seeded_user.id,
        frequency_unit="week",
        frequency_count=1,
        next_due_date=date(2026, 6, 1),
    )
    complete_task(db_session, task=task, user=seeded_user, today=date(2026, 6, 7))

    refreshed = get_task(db_session, task.id)
    assert refreshed is not None
    assert refreshed.active is True
    assert refreshed.next_due_date == date(2026, 6, 14)  # one week from completion
    assert refreshed.last_completed_by_id == seeded_user.id

    completions = list_recent_completions(db_session)
    assert len(completions) == 1
    assert completions[0].due_on == date(2026, 6, 1)


def test_complete_one_off_archives(db_session: Session, seeded_user: User) -> None:
    task = create_task(
        db_session,
        name="Fix the gate",
        details=None,
        assignee_id=None,
        frequency_unit="once",
        frequency_count=1,
        next_due_date=date(2026, 6, 7),
    )
    complete_task(db_session, task=task, user=seeded_user, today=date(2026, 6, 7))

    refreshed = get_task(db_session, task.id)
    assert refreshed is not None
    assert refreshed.active is False
    assert list_active_tasks(db_session) == []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_list_and_create_flow(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    assert authenticated_client.get("/tasks").status_code == 200

    resp = authenticated_client.post(
        "/tasks",
        data={
            "name": "Vacuum",
            "frequency_unit": "week",
            "frequency_count": "1",
            "next_due_date": "2026-06-07",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    tasks = list_active_tasks(db_session)
    assert len(tasks) == 1
    assert tasks[0].name == "Vacuum"

    assert authenticated_client.get("/tasks/history").status_code == 200


def test_create_requires_name(authenticated_client: TestClient) -> None:
    resp = authenticated_client.post(
        "/tasks",
        data={"name": "", "frequency_unit": "week", "next_due_date": "2026-06-07"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Name is required" in resp.text


def test_done_route_reschedules(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    task = create_task(
        db_session,
        name="Water plants",
        details=None,
        assignee_id=None,
        frequency_unit="day",
        frequency_count=2,
        next_due_date=date(2026, 6, 1),
    )
    resp = authenticated_client.post(f"/tasks/{task.id}/done", follow_redirects=False)
    assert resp.status_code == 303
    assert len(list_recent_completions(db_session)) == 1


def test_delete_removes_task(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    task = create_task(
        db_session,
        name="Temp",
        details=None,
        assignee_id=None,
        frequency_unit="week",
        frequency_count=1,
        next_due_date=date(2026, 6, 7),
    )
    resp = authenticated_client.post(f"/tasks/{task.id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert list_active_tasks(db_session) == []
