"""Projects-tracker router (PRD Section 21, Phase 4 item 2).

Mounts a per-user, private projects tracker at ``/projects``: a list of the
caller's own projects, each with a detail page carrying a dated-milestone
checklist and a journal. Every route requires a logged-in adult AND scopes to
the current user — a project is only ever reachable by its owner (unlike Tasks /
Lessons, which are household-shared). Completing a milestone auto-writes a
journal line; the project's status is set manually via the edit form.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.projects.models import PROJECT_STATUSES, STATUS_LABELS, Project
from family_assistant.projects.services import (
    add_entry,
    add_milestone,
    create_project,
    delete_entry,
    delete_milestone,
    delete_project,
    get_project,
    list_projects,
    toggle_milestone,
    update_project,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(require_user)],
)


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_optional_date(value: str) -> tuple[date | None, str | None]:
    """Optional date: empty is valid (None); a bad format is an error."""
    cleaned = (value or "").strip()
    if not cleaned:
        return None, None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Dates must be in YYYY-MM-DD format."


def _parse_entry_date(value: str) -> date:
    """Journal entry date: defaults to today when empty/invalid."""
    cleaned = (value or "").strip()
    if not cleaned:
        return date.today()
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _render_form(
    request: Request,
    *,
    project: Project | None,
    user: User,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "projects/form.html",
        {
            "project": project,
            "user": user,
            "statuses": PROJECT_STATUSES,
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
    projects = list_projects(db, user=user)
    return templates.TemplateResponse(
        request,
        "projects/list.html",
        {"projects": projects, "user": user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Create (literal /new before /{project_id})
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    user: Annotated[User, Depends(require_user)],
) -> Response:
    return _render_form(request, project=None, user=user, error=None)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    name: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "active",
    goal: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
) -> Response:
    form_data = {"name": name, "status": status, "goal": goal, "target_date": target_date}
    if not name.strip():
        return _render_form(
            request,
            project=None,
            user=user,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    target, target_err = _parse_optional_date(target_date)
    if target_err:
        return _render_form(
            request,
            project=None,
            user=user,
            error=target_err,
            form_data=form_data,
            status_code=400,
        )
    project = create_project(
        db,
        user=user,
        name=name,
        status=status,
        goal=goal or None,
        target_date=target,
    )
    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


# ---------------------------------------------------------------------------
# Milestone + entry actions (literal segments before /{project_id})
# ---------------------------------------------------------------------------


@router.post("/milestones/{milestone_id}/toggle")
def toggle_milestone_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    milestone_id: int,
) -> Response:
    project_id = toggle_milestone(db, milestone_id, user=user)
    return RedirectResponse(url=f"/projects/{project_id or ''}", status_code=303)


@router.post("/milestones/{milestone_id}/delete")
def delete_milestone_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    milestone_id: int,
) -> Response:
    project_id = delete_milestone(db, milestone_id, user=user)
    return RedirectResponse(url=f"/projects/{project_id or ''}", status_code=303)


@router.post("/entries/{entry_id}/delete")
def delete_entry_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    entry_id: int,
) -> Response:
    project_id = delete_entry(db, entry_id, user=user)
    return RedirectResponse(url=f"/projects/{project_id or ''}", status_code=303)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{project_id}", response_class=HTMLResponse)
def detail_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
) -> Response:
    project = get_project(db, project_id, user=user)
    if project is None:
        return RedirectResponse(url="/projects", status_code=303)
    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {"project": project, "user": user, "today": date.today()},
    )


# ---------------------------------------------------------------------------
# Edit / update / delete project
# ---------------------------------------------------------------------------


@router.get("/{project_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
) -> Response:
    project = get_project(db, project_id, user=user)
    if project is None:
        return RedirectResponse(url="/projects", status_code=303)
    return _render_form(request, project=project, user=user, error=None)


@router.post("/{project_id}")
def update_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
    name: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "active",
    goal: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
) -> Response:
    project = get_project(db, project_id, user=user)
    if project is None:
        return RedirectResponse(url="/projects", status_code=303)
    form_data = {"name": name, "status": status, "goal": goal, "target_date": target_date}
    if not name.strip():
        return _render_form(
            request,
            project=project,
            user=user,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    target, target_err = _parse_optional_date(target_date)
    if target_err:
        return _render_form(
            request,
            project=project,
            user=user,
            error=target_err,
            form_data=form_data,
            status_code=400,
        )
    update_project(
        db,
        project_id=project_id,
        user=user,
        name=name,
        status=status,
        goal=goal or None,
        target_date=target,
    )
    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


@router.post("/{project_id}/delete")
def delete_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
) -> Response:
    delete_project(db, project_id, user=user)
    return RedirectResponse(url="/projects", status_code=303)


# ---------------------------------------------------------------------------
# Nested creates (milestones / journal entries) under a project
# ---------------------------------------------------------------------------


@router.post("/{project_id}/milestones")
def add_milestone_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
    title: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
) -> Response:
    if title.strip():
        target, _ = _parse_optional_date(target_date)
        add_milestone(db, project_id=project_id, user=user, title=title, target_date=target)
    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


@router.post("/{project_id}/entries")
def add_entry_view(
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    project_id: int,
    note: Annotated[str, Form()] = "",
    entry_date: Annotated[str, Form()] = "",
    link: Annotated[str, Form()] = "",
) -> Response:
    if note.strip():
        add_entry(
            db,
            project_id=project_id,
            user=user,
            entry_date=_parse_entry_date(entry_date),
            note=note,
            link=link or None,
        )
    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)
