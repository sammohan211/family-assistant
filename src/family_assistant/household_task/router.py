"""Household task router (PRD Section 21, Phase 4 item 1).

Mounts the shared chore board at ``/tasks``: a due-ordered to-do list with a
one-click Done action, plus a completion history view. Every route requires a
logged-in user, but tasks are household-shared — there's no per-user guard, as
with grocery / meal / lunch plans.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.household_task.models import FREQUENCY_UNITS, HouseholdTask
from family_assistant.household_task.services import (
    complete_task,
    create_task,
    delete_task,
    get_task,
    list_active_tasks,
    list_recent_completions,
    list_users,
    summarize,
    update_task,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/tasks",
    tags=["household_tasks"],
    dependencies=[Depends(require_user)],
)


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> tuple[date | None, str | None]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None, "Due date is required."
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Due date must be YYYY-MM-DD."


def _parse_assignee(raw: str) -> int | None:
    cleaned = (raw or "").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _parse_count(raw: str) -> int:
    cleaned = (raw or "").strip()
    try:
        return max(1, int(cleaned))
    except ValueError:
        return 1


def _render_form(
    request: Request,
    *,
    task: HouseholdTask | None,
    user: User,
    users: list[User],
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "household_task/form.html",
        {
            "task": task,
            "user": user,
            "users": users,
            "frequency_units": FREQUENCY_UNITS,
            "error": error,
            "form_data": form_data or {},
            "today": date.today(),
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# To-do list
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    tasks = list_active_tasks(db)
    today = date.today()
    return templates.TemplateResponse(
        request,
        "household_task/list.html",
        {"tasks": tasks, "user": user, "today": today, "counts": summarize(tasks, today=today)},
    )


@router.get("/history", response_class=HTMLResponse)
def history_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    completions = list_recent_completions(db)
    return templates.TemplateResponse(
        request,
        "household_task/history.html",
        {"completions": completions, "user": user},
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    return _render_form(request, task=None, user=user, users=list_users(db), error=None)


def _validate_and_save(
    *,
    request: Request,
    db: DbSession,
    user: User,
    task: HouseholdTask | None,
    name: str,
    details: str,
    assignee: str,
    frequency_unit: str,
    frequency_count: str,
    next_due_date: str,
    active: bool,
) -> Response:
    users = list_users(db)
    form_data = {
        "name": name,
        "details": details,
        "assignee": assignee,
        "frequency_unit": frequency_unit,
        "frequency_count": frequency_count,
        "next_due_date": next_due_date,
        "active": "on" if active else "",
    }

    cleaned_name = name.strip()
    if not cleaned_name:
        return _render_form(
            request,
            task=task,
            user=user,
            users=users,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    if frequency_unit not in FREQUENCY_UNITS:
        return _render_form(
            request,
            task=task,
            user=user,
            users=users,
            error="Pick a valid frequency.",
            form_data=form_data,
            status_code=400,
        )
    due, due_error = _parse_date(next_due_date)
    if due_error is not None:
        return _render_form(
            request,
            task=task,
            user=user,
            users=users,
            error=due_error,
            form_data=form_data,
            status_code=400,
        )
    assert due is not None

    assignee_id = _parse_assignee(assignee)
    count = _parse_count(frequency_count)

    if task is None:
        create_task(
            db,
            name=cleaned_name,
            details=details or None,
            assignee_id=assignee_id,
            frequency_unit=frequency_unit,
            frequency_count=count,
            next_due_date=due,
        )
    else:
        update_task(
            db,
            task_id=task.id,
            name=cleaned_name,
            details=details or None,
            assignee_id=assignee_id,
            frequency_unit=frequency_unit,
            frequency_count=count,
            next_due_date=due,
            active=active,
        )
    return RedirectResponse(url="/tasks", status_code=303)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    name: Annotated[str, Form()] = "",
    details: Annotated[str, Form()] = "",
    assignee: Annotated[str, Form()] = "",
    frequency_unit: Annotated[str, Form()] = "week",
    frequency_count: Annotated[str, Form()] = "1",
    next_due_date: Annotated[str, Form()] = "",
) -> Response:
    return _validate_and_save(
        request=request,
        db=db,
        user=user,
        task=None,
        name=name,
        details=details,
        assignee=assignee,
        frequency_unit=frequency_unit,
        frequency_count=frequency_count,
        next_due_date=next_due_date,
        active=True,
    )


# ---------------------------------------------------------------------------
# Done (declared before /{task_id} so the literal segment wins matching)
# ---------------------------------------------------------------------------


@router.post("/{task_id}/done")
def done_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    task_id: int,
) -> Response:
    task = get_task(db, task_id)
    if task is not None and task.active:
        complete_task(db, task=task, user=user)
    return RedirectResponse(url="/tasks", status_code=303)


@router.post("/{task_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    task_id: int,
) -> Response:
    delete_task(db, task_id)
    return RedirectResponse(url="/tasks", status_code=303)


# ---------------------------------------------------------------------------
# Edit / update
# ---------------------------------------------------------------------------


@router.get("/{task_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    task_id: int,
) -> Response:
    task = get_task(db, task_id)
    if task is None:
        return RedirectResponse(url="/tasks", status_code=303)
    return _render_form(request, task=task, user=user, users=list_users(db), error=None)


@router.post("/{task_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    task_id: int,
    name: Annotated[str, Form()] = "",
    details: Annotated[str, Form()] = "",
    assignee: Annotated[str, Form()] = "",
    frequency_unit: Annotated[str, Form()] = "week",
    frequency_count: Annotated[str, Form()] = "1",
    next_due_date: Annotated[str, Form()] = "",
    active: Annotated[str, Form()] = "",
) -> Response:
    task = get_task(db, task_id)
    if task is None:
        return RedirectResponse(url="/tasks", status_code=303)
    return _validate_and_save(
        request=request,
        db=db,
        user=user,
        task=task,
        name=name,
        details=details,
        assignee=assignee,
        frequency_unit=frequency_unit,
        frequency_count=frequency_count,
        next_due_date=next_due_date,
        active=bool(active),
    )
