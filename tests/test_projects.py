"""Projects module tests: the milestone auto-journal rule, the stale signal,
per-user isolation, plus service CRUD and the shared routes."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.auth.services import hash_password
from family_assistant.projects.models import STALE_AFTER_DAYS, ProjectEntry
from family_assistant.projects.services import (
    add_entry,
    add_milestone,
    create_project,
    delete_project,
    get_project,
    list_projects,
    toggle_milestone,
    update_project,
)


def _make_project(db: Session, user: User, name: str = "Build NAS", status: str = "active") -> int:
    project = create_project(
        db, user=user, name=name, status=status, goal="A goal", target_date=date(2026, 8, 31)
    )
    return project.id


def _other_user(db: Session) -> User:
    user = User(name="Bob", email="bob@example.com", password_hash=hash_password("x"))
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# Milestones + the auto-journal rule
# ---------------------------------------------------------------------------


def test_toggle_milestone_writes_and_removes_journal_line(
    db_session: Session, seeded_user: User
) -> None:
    project_id = _make_project(db_session, seeded_user)
    milestone = add_milestone(
        db_session, project_id=project_id, user=seeded_user, title="Buy drives", target_date=None
    )
    assert milestone is not None and milestone.done is False

    # Completing it auto-writes one journal line tagged with the milestone.
    toggle_milestone(db_session, milestone.id, user=seeded_user)
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.milestones_done == 1
    autos = [e for e in project.entries if e.is_auto]
    assert len(autos) == 1
    assert "Buy drives" in autos[0].note
    assert project.milestones[0].done_at is not None

    # Un-completing removes that auto-line again.
    toggle_milestone(db_session, milestone.id, user=seeded_user)
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.milestones_done == 0
    assert [e for e in project.entries if e.is_auto] == []


def test_manual_journal_entries_survive_milestone_untoggle(
    db_session: Session, seeded_user: User
) -> None:
    project_id = _make_project(db_session, seeded_user)
    add_entry(
        db_session,
        project_id=project_id,
        user=seeded_user,
        entry_date=date.today(),
        note="Manual note",
        link=None,
    )
    milestone = add_milestone(
        db_session, project_id=project_id, user=seeded_user, title="MS", target_date=None
    )
    toggle_milestone(db_session, milestone.id, user=seeded_user)
    toggle_milestone(db_session, milestone.id, user=seeded_user)
    project = get_project(db_session, project_id, user=seeded_user)
    # The manual note remains; only the auto-line was cleaned up.
    notes = [e.note for e in project.entries]
    assert notes == ["Manual note"]


def test_milestone_positions_increment(db_session: Session, seeded_user: User) -> None:
    project_id = _make_project(db_session, seeded_user)
    first = add_milestone(
        db_session, project_id=project_id, user=seeded_user, title="A", target_date=None
    )
    second = add_milestone(
        db_session, project_id=project_id, user=seeded_user, title="B", target_date=None
    )
    assert first.position == 0
    assert second.position == 1


# ---------------------------------------------------------------------------
# last_touched / stale signal
# ---------------------------------------------------------------------------


def test_last_touched_and_stale_signal(db_session: Session, seeded_user: User) -> None:
    today = date(2026, 7, 1)
    project_id = _make_project(db_session, seeded_user)
    project = get_project(db_session, project_id, user=seeded_user)

    old = today - timedelta(days=STALE_AFTER_DAYS + 5)
    add_entry(
        db_session, project_id=project_id, user=seeded_user, entry_date=old, note="old", link=None
    )
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.last_touched == old
    assert project.is_stale(today) is True

    # A fresh note clears the stale flag.
    add_entry(
        db_session,
        project_id=project_id,
        user=seeded_user,
        entry_date=today,
        note="fresh",
        link=None,
    )
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.last_touched == today
    assert project.is_stale(today) is False


def test_closed_projects_never_stale(db_session: Session, seeded_user: User) -> None:
    today = date(2026, 7, 1)
    project_id = _make_project(db_session, seeded_user, status="done")
    old = today - timedelta(days=STALE_AFTER_DAYS + 30)
    add_entry(
        db_session, project_id=project_id, user=seeded_user, entry_date=old, note="x", link=None
    )
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.is_stale(today) is False


# ---------------------------------------------------------------------------
# Per-user isolation
# ---------------------------------------------------------------------------


def test_projects_are_private_per_user(db_session: Session, seeded_user: User) -> None:
    bob = _other_user(db_session)
    bob_project_id = _make_project(db_session, bob, name="Bob's secret")

    # Alice (seeded_user) cannot see or fetch Bob's project.
    assert get_project(db_session, bob_project_id, user=seeded_user) is None
    assert list_projects(db_session, user=seeded_user) == []
    assert len(list_projects(db_session, user=bob)) == 1

    # Nor can she mutate it through the service layer.
    assert (
        update_project(
            db_session,
            project_id=bob_project_id,
            user=seeded_user,
            name="hacked",
            status="active",
            goal=None,
            target_date=None,
        )
        is None
    )
    assert delete_project(db_session, bob_project_id, user=seeded_user) is False
    # Bob's row is untouched.
    assert get_project(db_session, bob_project_id, user=bob).name == "Bob's secret"


def test_cannot_toggle_another_users_milestone(db_session: Session, seeded_user: User) -> None:
    bob = _other_user(db_session)
    bob_project_id = _make_project(db_session, bob)
    milestone = add_milestone(
        db_session, project_id=bob_project_id, user=bob, title="MS", target_date=None
    )
    # Alice's toggle is rejected (returns None, no state change).
    assert toggle_milestone(db_session, milestone.id, user=seeded_user) is None
    assert get_project(db_session, bob_project_id, user=bob).milestones_done == 0


# ---------------------------------------------------------------------------
# Status handling + ordering
# ---------------------------------------------------------------------------


def test_invalid_status_clamps_to_active(db_session: Session, seeded_user: User) -> None:
    project = create_project(
        db_session, user=seeded_user, name="P", status="bogus", goal=None, target_date=None
    )
    assert project.status == "active"


def test_open_projects_sort_before_closed(db_session: Session, seeded_user: User) -> None:
    open_id = _make_project(db_session, seeded_user, name="Open one", status="active")
    done_id = _make_project(db_session, seeded_user, name="Done one", status="done")
    ordered = [p.id for p in list_projects(db_session, user=seeded_user)]
    assert ordered.index(open_id) < ordered.index(done_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_routes_create_through_milestone(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    assert authenticated_client.get("/projects").status_code == 200

    resp = authenticated_client.post(
        "/projects",
        data={"name": "Learn Rust", "status": "active", "target_date": "2026-09-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    project_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
    assert authenticated_client.get(f"/projects/{project_id}").status_code == 200

    # Add a milestone, then complete it → auto journal line appears.
    authenticated_client.post(
        f"/projects/{project_id}/milestones",
        data={"title": "Read the book"},
        follow_redirects=False,
    )
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.milestones_total == 1
    authenticated_client.post(
        f"/projects/milestones/{project.milestones[0].id}/toggle", follow_redirects=False
    )
    project = get_project(db_session, project_id, user=seeded_user)
    assert project.milestones_done == 1
    assert any(e.is_auto for e in project.entries)


def test_create_requires_name(authenticated_client: TestClient) -> None:
    resp = authenticated_client.post("/projects", data={"name": ""}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Name is required" in resp.text


def test_detail_route_hides_other_users_project(
    authenticated_client: TestClient, db_session: Session
) -> None:
    bob = _other_user(db_session)
    bob_project_id = _make_project(db_session, bob)
    # Alice gets bounced back to the list instead of seeing Bob's project.
    resp = authenticated_client.get(f"/projects/{bob_project_id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/projects"


def test_delete_project_route(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    project_id = _make_project(db_session, seeded_user)
    resp = authenticated_client.post(f"/projects/{project_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert get_project(db_session, project_id, user=seeded_user) is None


def test_add_journal_entry_route(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    project_id = _make_project(db_session, seeded_user)
    authenticated_client.post(
        f"/projects/{project_id}/entries",
        data={"note": "Made progress", "link": "https://example.com"},
        follow_redirects=False,
    )
    entries = db_session.query(ProjectEntry).filter_by(project_id=project_id).all()
    assert len(entries) == 1
    assert entries[0].note == "Made progress"
    assert entries[0].link == "https://example.com"
