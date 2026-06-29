"""Lessons module tests: the test-completion gate (a lesson is done iff its
test is checked) plus service CRUD and the shared routes."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.lessons.services import (
    add_objective,
    create_lesson,
    get_lesson,
    list_lessons,
    set_test,
    toggle_objective,
    toggle_test,
    update_lesson,
)


def _make_lesson(db: Session, title: str = "Times tables") -> int:
    lesson = create_lesson(
        db,
        title=title,
        subject="Math",
        description=None,
        start_date=date(2026, 7, 1),
        end_date=None,
    )
    return lesson.id


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------


def test_toggle_objective_sets_done_and_nudges_status(db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)
    objective = add_objective(
        db_session, lesson_id=lesson_id, title="Learn 2x", scheduled_date=None
    )
    assert objective is not None
    assert objective.done is False

    toggled = toggle_objective(db_session, objective.id)
    assert toggled is not None
    assert toggled.done is True
    assert toggled.done_at is not None
    # First completed objective moves a planned lesson to "in progress".
    assert get_lesson(db_session, lesson_id).status == "in_progress"

    untoggled = toggle_objective(db_session, objective.id)
    assert untoggled.done is False
    assert untoggled.done_at is None


def test_objective_positions_increment(db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)
    first = add_objective(db_session, lesson_id=lesson_id, title="A", scheduled_date=None)
    second = add_objective(db_session, lesson_id=lesson_id, title="B", scheduled_date=None)
    assert first.position == 0
    assert second.position == 1


# ---------------------------------------------------------------------------
# Test as the completion gate
# ---------------------------------------------------------------------------


def test_lesson_completes_only_via_test(db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)

    # No test yet → toggle is a no-op, lesson can't be done.
    assert toggle_test(db_session, lesson_id) is None
    assert get_lesson(db_session, lesson_id).status != "done"

    set_test(db_session, lesson_id=lesson_id, title="Quiz", score=None, notes=None)
    assert get_lesson(db_session, lesson_id).has_test is True
    assert get_lesson(db_session, lesson_id).status != "done"  # added, not yet passed

    test = toggle_test(db_session, lesson_id)
    assert test is not None and test.done is True and test.done_at is not None
    lesson = get_lesson(db_session, lesson_id)
    assert lesson.status == "done"
    assert lesson.is_complete is True

    # Unchecking drops the lesson back out of done.
    toggle_test(db_session, lesson_id)
    lesson = get_lesson(db_session, lesson_id)
    assert lesson.status == "in_progress"
    assert lesson.is_complete is False


def test_update_lesson_cannot_force_done(db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)
    update_lesson(
        db_session,
        lesson_id=lesson_id,
        title="Times tables",
        subject="Math",
        description=None,
        status="done",  # not allowed from the form path
        start_date=None,
        end_date=None,
    )
    assert get_lesson(db_session, lesson_id).status == "planned"


def test_set_test_is_idempotent_one_per_lesson(db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)
    set_test(db_session, lesson_id=lesson_id, title="Quiz v1", score=None, notes=None)
    set_test(db_session, lesson_id=lesson_id, title="Quiz v2", score="9/10", notes="great")
    lesson = get_lesson(db_session, lesson_id)
    assert lesson.test is not None
    assert lesson.test.title == "Quiz v2"
    assert lesson.test.score == "9/10"


def test_done_lessons_sort_after_active(db_session: Session) -> None:
    active_id = _make_lesson(db_session, title="Active lesson")
    done_id = _make_lesson(db_session, title="Done lesson")
    set_test(db_session, lesson_id=done_id, title="Quiz", score=None, notes=None)
    toggle_test(db_session, done_id)

    ordered = [lesson.id for lesson in list_lessons(db_session)]
    assert ordered.index(active_id) < ordered.index(done_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_routes_create_through_complete(
    authenticated_client: TestClient, db_session: Session
) -> None:
    # List loads.
    assert authenticated_client.get("/lessons").status_code == 200

    # Create → redirects to detail.
    resp = authenticated_client.post(
        "/lessons",
        data={"title": "Reading", "subject": "English", "start_date": "2026-07-05"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    lesson_id = int(resp.headers["location"].rstrip("/").split("/")[-1])
    assert authenticated_client.get(f"/lessons/{lesson_id}").status_code == 200

    # Add an objective and toggle it.
    authenticated_client.post(
        f"/lessons/{lesson_id}/objectives",
        data={"title": "Read chapter 1"},
        follow_redirects=False,
    )
    lesson = get_lesson(db_session, lesson_id)
    assert lesson.objectives_total == 1
    authenticated_client.post(
        f"/lessons/objectives/{lesson.objectives[0].id}/toggle", follow_redirects=False
    )
    assert get_lesson(db_session, lesson_id).objectives_done == 1

    # Add the test, then pass it → lesson done.
    authenticated_client.post(
        f"/lessons/{lesson_id}/test", data={"title": "Comprehension quiz"}, follow_redirects=False
    )
    authenticated_client.post(f"/lessons/{lesson_id}/test/toggle", follow_redirects=False)
    assert get_lesson(db_session, lesson_id).status == "done"


def test_create_requires_title(authenticated_client: TestClient) -> None:
    resp = authenticated_client.post("/lessons", data={"title": ""}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Title is required" in resp.text


def test_delete_lesson_route(authenticated_client: TestClient, db_session: Session) -> None:
    lesson_id = _make_lesson(db_session)
    resp = authenticated_client.post(f"/lessons/{lesson_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert get_lesson(db_session, lesson_id) is None
