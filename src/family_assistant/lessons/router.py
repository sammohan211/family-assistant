"""Lessons-plan router (PRD Section 21, Phase 4 item 3).

Mounts a parent-curated home-learning plan at ``/lessons``: a list of lessons,
each a detail page with an ordered objectives checklist, resource links, and a
single end-of-lesson test whose check-off marks the lesson done. Every route
requires a logged-in adult, but lessons are household-shared — no per-user
guard, as with Tasks / grocery / meal / lunch plans. There is only one kid, so
there is no FamilyMember selector.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.lessons.models import EDITABLE_STATUSES, STATUS_LABELS, Lesson
from family_assistant.lessons.services import (
    add_objective,
    add_resource,
    create_lesson,
    delete_lesson,
    delete_objective,
    delete_resource,
    get_lesson,
    list_lessons,
    set_test,
    toggle_objective,
    toggle_test,
    update_lesson,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/lessons",
    tags=["lessons"],
    dependencies=[Depends(require_user)],
)


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> tuple[date | None, str | None]:
    """Optional date: empty is valid (None); a bad format is an error."""
    cleaned = (value or "").strip()
    if not cleaned:
        return None, None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Dates must be in YYYY-MM-DD format."


def _parse_optional_int(raw: str) -> int | None:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _render_form(
    request: Request,
    *,
    lesson: Lesson | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "lessons/form.html",
        {
            "lesson": lesson,
            "user": user,
            "editable_statuses": EDITABLE_STATUSES,
            "status_labels": STATUS_LABELS,
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    lessons = list_lessons(db)
    return templates.TemplateResponse(
        request,
        "lessons/list.html",
        {"lessons": lessons, "user": user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Create (literal /new before /{lesson_id})
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    user: Annotated[User, Depends(require_user)],
) -> Response:
    return _render_form(request, lesson=None, user=user, error=None)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    title: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    start_date: Annotated[str, Form()] = "",
    end_date: Annotated[str, Form()] = "",
) -> Response:
    form_data = {
        "title": title,
        "subject": subject,
        "description": description,
        "start_date": start_date,
        "end_date": end_date,
    }
    if not title.strip():
        return _render_form(
            request,
            lesson=None,
            user=user,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    start, start_err = _parse_date(start_date)
    end, end_err = _parse_date(end_date)
    if start_err or end_err:
        return _render_form(
            request,
            lesson=None,
            user=user,
            error=start_err or end_err,
            form_data=form_data,
            status_code=400,
        )
    lesson = create_lesson(
        db,
        title=title,
        subject=subject or None,
        description=description or None,
        start_date=start,
        end_date=end,
    )
    return RedirectResponse(url=f"/lessons/{lesson.id}", status_code=303)


# ---------------------------------------------------------------------------
# Objective + resource actions (literal segments before /{lesson_id})
# ---------------------------------------------------------------------------


@router.post("/objectives/{objective_id}/toggle")
def toggle_objective_view(
    db: Annotated[DbSession, Depends(get_session)],
    objective_id: int,
) -> Response:
    objective = toggle_objective(db, objective_id)
    target = objective.lesson_id if objective is not None else ""
    return RedirectResponse(url=f"/lessons/{target}", status_code=303)


@router.post("/objectives/{objective_id}/delete")
def delete_objective_view(
    db: Annotated[DbSession, Depends(get_session)],
    objective_id: int,
) -> Response:
    lesson_id = delete_objective(db, objective_id)
    return RedirectResponse(url=f"/lessons/{lesson_id or ''}", status_code=303)


@router.post("/resources/{resource_id}/delete")
def delete_resource_view(
    db: Annotated[DbSession, Depends(get_session)],
    resource_id: int,
) -> Response:
    lesson_id = delete_resource(db, resource_id)
    return RedirectResponse(url=f"/lessons/{lesson_id or ''}", status_code=303)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{lesson_id}", response_class=HTMLResponse)
def detail_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    lesson_id: int,
) -> Response:
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return RedirectResponse(url="/lessons", status_code=303)
    return templates.TemplateResponse(
        request,
        "lessons/detail.html",
        {"lesson": lesson, "user": user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Edit / update / delete lesson
# ---------------------------------------------------------------------------


@router.get("/{lesson_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    lesson_id: int,
) -> Response:
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return RedirectResponse(url="/lessons", status_code=303)
    return _render_form(request, lesson=lesson, user=user, error=None)


@router.post("/{lesson_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    lesson_id: int,
    title: Annotated[str, Form()] = "",
    subject: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "planned",
    start_date: Annotated[str, Form()] = "",
    end_date: Annotated[str, Form()] = "",
) -> Response:
    lesson = get_lesson(db, lesson_id)
    if lesson is None:
        return RedirectResponse(url="/lessons", status_code=303)
    form_data = {
        "title": title,
        "subject": subject,
        "description": description,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
    }
    if not title.strip():
        return _render_form(
            request,
            lesson=lesson,
            user=user,
            error="Title is required.",
            form_data=form_data,
            status_code=400,
        )
    start, start_err = _parse_date(start_date)
    end, end_err = _parse_date(end_date)
    if start_err or end_err:
        return _render_form(
            request,
            lesson=lesson,
            user=user,
            error=start_err or end_err,
            form_data=form_data,
            status_code=400,
        )
    update_lesson(
        db,
        lesson_id=lesson_id,
        title=title,
        subject=subject or None,
        description=description or None,
        status=status,
        start_date=start,
        end_date=end,
    )
    return RedirectResponse(url=f"/lessons/{lesson_id}", status_code=303)


@router.post("/{lesson_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    lesson_id: int,
) -> Response:
    delete_lesson(db, lesson_id)
    return RedirectResponse(url="/lessons", status_code=303)


# ---------------------------------------------------------------------------
# Nested creates (objectives / resources / test) under a lesson
# ---------------------------------------------------------------------------


@router.post("/{lesson_id}/objectives")
def add_objective_view(
    db: Annotated[DbSession, Depends(get_session)],
    lesson_id: int,
    title: Annotated[str, Form()] = "",
    scheduled_date: Annotated[str, Form()] = "",
) -> Response:
    if title.strip():
        scheduled, _ = _parse_date(scheduled_date)
        add_objective(db, lesson_id=lesson_id, title=title, scheduled_date=scheduled)
    return RedirectResponse(url=f"/lessons/{lesson_id}", status_code=303)


@router.post("/{lesson_id}/resources")
def add_resource_view(
    db: Annotated[DbSession, Depends(get_session)],
    lesson_id: int,
    label: Annotated[str, Form()] = "",
    url: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    objective_id: Annotated[str, Form()] = "",
) -> Response:
    if label.strip():
        add_resource(
            db,
            lesson_id=lesson_id,
            objective_id=_parse_optional_int(objective_id),
            label=label,
            url=url or None,
            note=note or None,
        )
    return RedirectResponse(url=f"/lessons/{lesson_id}", status_code=303)


@router.post("/{lesson_id}/test")
def set_test_view(
    db: Annotated[DbSession, Depends(get_session)],
    lesson_id: int,
    title: Annotated[str, Form()] = "",
    score: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    if title.strip():
        set_test(db, lesson_id=lesson_id, title=title, score=score or None, notes=notes or None)
    return RedirectResponse(url=f"/lessons/{lesson_id}", status_code=303)


@router.post("/{lesson_id}/test/toggle")
def toggle_test_view(
    db: Annotated[DbSession, Depends(get_session)],
    lesson_id: int,
) -> Response:
    toggle_test(db, lesson_id)
    return RedirectResponse(url=f"/lessons/{lesson_id}", status_code=303)
