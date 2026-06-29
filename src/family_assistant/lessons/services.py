"""Lessons-plan CRUD + completion services (PRD Section 21, Phase 4 item 3).

Lessons are household-shared, so reads/writes are not scoped to a user. Two
rules are locked here rather than left to the UI:

  - **Checking off a lesson's test is what marks the lesson done.** A lesson
    cannot reach ``status == "done"`` any other way (the edit form only offers
    "planned" / "in progress"); unchecking the test drops it back.
  - **Every lesson ends with exactly one test.** ``set_test`` creates it on
    first save and updates it thereafter; the unique constraint on
    ``lesson_id`` backs this up at the DB level.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.lessons.models import (
    EDITABLE_STATUSES,
    LearningObjective,
    Lesson,
    LessonResource,
    LessonTest,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Lesson CRUD
# ---------------------------------------------------------------------------


def _loaded(statement):
    return statement.options(
        selectinload(Lesson.objectives),
        selectinload(Lesson.resources),
        selectinload(Lesson.test),
    )


def list_lessons(db: DbSession) -> list[Lesson]:
    """All lessons, active first then done; within each, by start date (NULLs
    last, the Postgres default for ASC) then title."""
    statement = _loaded(
        select(Lesson).order_by(
            (Lesson.status == "done"),
            Lesson.start_date.asc(),
            Lesson.title.asc(),
        )
    )
    return list(db.scalars(statement).all())


def get_lesson(db: DbSession, lesson_id: int) -> Lesson | None:
    statement = _loaded(select(Lesson).where(Lesson.id == lesson_id))
    return db.scalars(statement).first()


def create_lesson(
    db: DbSession,
    *,
    title: str,
    subject: str | None,
    description: str | None,
    start_date: date | None,
    end_date: date | None,
) -> Lesson:
    lesson = Lesson(
        title=title.strip(),
        subject=subject.strip() if subject else None,
        description=description.strip() if description else None,
        start_date=start_date,
        end_date=end_date,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def update_lesson(
    db: DbSession,
    *,
    lesson_id: int,
    title: str,
    subject: str | None,
    description: str | None,
    status: str,
    start_date: date | None,
    end_date: date | None,
) -> Lesson | None:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        return None
    # "done" is reserved for the test toggle — never settable from the form.
    if status not in EDITABLE_STATUSES:
        status = "planned"
    lesson.title = title.strip()
    lesson.subject = subject.strip() if subject else None
    lesson.description = description.strip() if description else None
    lesson.status = status
    lesson.start_date = start_date
    lesson.end_date = end_date
    db.commit()
    db.refresh(lesson)
    return lesson


def delete_lesson(db: DbSession, lesson_id: int) -> bool:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        return False
    db.delete(lesson)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------


def _next_position(items: list) -> int:
    return max((i.position for i in items), default=-1) + 1


def add_objective(
    db: DbSession,
    *,
    lesson_id: int,
    title: str,
    scheduled_date: date | None,
) -> LearningObjective | None:
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return None
    objective = LearningObjective(
        lesson_id=lesson_id,
        title=title.strip(),
        scheduled_date=scheduled_date,
        position=_next_position(lesson.objectives),
    )
    db.add(objective)
    db.commit()
    db.refresh(objective)
    return objective


def toggle_objective(db: DbSession, objective_id: int) -> LearningObjective | None:
    objective = db.get(LearningObjective, objective_id)
    if objective is None:
        return None
    objective.done = not objective.done
    objective.done_at = _now() if objective.done else None
    # Starting to work through a planned lesson nudges it to "in progress".
    lesson = db.get(Lesson, objective.lesson_id)
    if lesson is not None and lesson.status == "planned" and objective.done:
        lesson.status = "in_progress"
    db.commit()
    db.refresh(objective)
    return objective


def delete_objective(db: DbSession, objective_id: int) -> int | None:
    """Delete an objective; returns its lesson_id (for redirecting) or None."""
    objective = db.get(LearningObjective, objective_id)
    if objective is None:
        return None
    lesson_id = objective.lesson_id
    db.delete(objective)
    db.commit()
    return lesson_id


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def add_resource(
    db: DbSession,
    *,
    lesson_id: int,
    objective_id: int | None,
    label: str,
    url: str | None,
    note: str | None,
) -> LessonResource | None:
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return None
    resource = LessonResource(
        lesson_id=lesson_id,
        objective_id=objective_id,
        label=label.strip(),
        url=url.strip() if url else None,
        note=note.strip() if note else None,
        position=_next_position(lesson.resources),
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def delete_resource(db: DbSession, resource_id: int) -> int | None:
    """Delete a resource; returns its lesson_id (for redirecting) or None."""
    resource = db.get(LessonResource, resource_id)
    if resource is None:
        return None
    lesson_id = resource.lesson_id
    db.delete(resource)
    db.commit()
    return lesson_id


# ---------------------------------------------------------------------------
# Test (one per lesson; the completion gate)
# ---------------------------------------------------------------------------


def set_test(
    db: DbSession,
    *,
    lesson_id: int,
    title: str,
    score: str | None,
    notes: str | None,
) -> LessonTest | None:
    """Create the lesson's test on first save, or update it thereafter."""
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return None
    test = lesson.test
    if test is None:
        test = LessonTest(lesson_id=lesson_id, title=title.strip())
        db.add(test)
    else:
        test.title = title.strip()
    test.score = score.strip() if score else None
    test.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(test)
    return test


def toggle_test(db: DbSession, lesson_id: int) -> LessonTest | None:
    """Flip the test's done flag and move the lesson in/out of ``done``.

    This is the *only* path to a "done" lesson — the rule that a lesson can't
    be complete without its test lives here.
    """
    lesson = get_lesson(db, lesson_id)
    if lesson is None or lesson.test is None:
        return None
    test = lesson.test
    test.done = not test.done
    if test.done:
        test.done_at = _now()
        lesson.status = "done"
    else:
        test.done_at = None
        lesson.status = "in_progress"
    db.commit()
    db.refresh(test)
    return test
