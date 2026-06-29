"""Projects-tracker CRUD + journal services (PRD Section 21, Phase 4 item 2).

Projects are **per-user and private**, so every read and write is scoped to the
owning user — a project (and its milestones / journal entries) is only ever
reachable by the user whose ``user_id`` it carries. Routes pass the current
user; the ``get_project`` / ``_owned_*`` helpers enforce ownership and return
``None`` for anything that isn't the caller's.

One rule is locked here rather than left to the UI:

  - **Completing a milestone auto-writes a journal entry** ("Completed
    milestone: …"), linking the breakdown to the timeline. Un-completing the
    milestone removes that auto-line. Manual notes are never auto-managed.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.projects.models import (
    CLOSED_STATUSES,
    PROJECT_STATUSES,
    Project,
    ProjectEntry,
    ProjectMilestone,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _loaded(statement):
    return statement.options(
        selectinload(Project.milestones),
        selectinload(Project.entries),
    )


# ---------------------------------------------------------------------------
# Project CRUD (all scoped to the owning user)
# ---------------------------------------------------------------------------


def list_projects(db: DbSession, *, user: User) -> list[Project]:
    """The user's own projects: open ones first (then closed), within each by
    target date (NULLs last, the Postgres default for ASC) then name."""
    statement = _loaded(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(
            Project.status.in_(CLOSED_STATUSES),
            Project.target_date.asc(),
            Project.name.asc(),
        )
    )
    return list(db.scalars(statement).all())


def get_project(db: DbSession, project_id: int, *, user: User) -> Project | None:
    """Fetch one project, but only if it belongs to ``user``."""
    statement = _loaded(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    return db.scalars(statement).first()


def create_project(
    db: DbSession,
    *,
    user: User,
    name: str,
    status: str,
    goal: str | None,
    target_date: date | None,
) -> Project:
    if status not in PROJECT_STATUSES:
        status = "active"
    project = Project(
        user_id=user.id,
        name=name.strip(),
        status=status,
        goal=goal.strip() if goal else None,
        target_date=target_date,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: DbSession,
    *,
    project_id: int,
    user: User,
    name: str,
    status: str,
    goal: str | None,
    target_date: date | None,
) -> Project | None:
    project = get_project(db, project_id, user=user)
    if project is None:
        return None
    if status not in PROJECT_STATUSES:
        status = project.status
    project.name = name.strip()
    project.status = status
    project.goal = goal.strip() if goal else None
    project.target_date = target_date
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: DbSession, project_id: int, *, user: User) -> bool:
    project = get_project(db, project_id, user=user)
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def _next_position(items: list) -> int:
    return max((i.position for i in items), default=-1) + 1


def _owned_milestone(db: DbSession, milestone_id: int, *, user: User) -> ProjectMilestone | None:
    """A milestone, only if its project belongs to ``user``."""
    milestone = db.get(ProjectMilestone, milestone_id)
    if milestone is None:
        return None
    project = db.get(Project, milestone.project_id)
    if project is None or project.user_id != user.id:
        return None
    return milestone


def add_milestone(
    db: DbSession,
    *,
    project_id: int,
    user: User,
    title: str,
    target_date: date | None,
) -> ProjectMilestone | None:
    project = get_project(db, project_id, user=user)
    if project is None:
        return None
    milestone = ProjectMilestone(
        project_id=project_id,
        title=title.strip(),
        target_date=target_date,
        position=_next_position(project.milestones),
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


def toggle_milestone(db: DbSession, milestone_id: int, *, user: User) -> int | None:
    """Flip a milestone's done flag; returns its project_id (for redirect).

    Completing a milestone auto-writes a journal entry; un-completing removes
    that auto-line. This auto-journal rule lives here, not in the UI.
    """
    milestone = _owned_milestone(db, milestone_id, user=user)
    if milestone is None:
        return None
    milestone.done = not milestone.done
    if milestone.done:
        milestone.done_at = _now()
        db.add(
            ProjectEntry(
                project_id=milestone.project_id,
                entry_date=date.today(),
                note=f"Completed milestone: {milestone.title}",
                milestone_id=milestone.id,
            )
        )
    else:
        milestone.done_at = None
        # Drop the auto-written journal line for this milestone, if present.
        auto = db.scalars(
            select(ProjectEntry).where(ProjectEntry.milestone_id == milestone.id)
        ).all()
        for entry in auto:
            db.delete(entry)
    db.commit()
    return milestone.project_id


def delete_milestone(db: DbSession, milestone_id: int, *, user: User) -> int | None:
    """Delete a milestone; returns its project_id (for redirect) or None."""
    milestone = _owned_milestone(db, milestone_id, user=user)
    if milestone is None:
        return None
    project_id = milestone.project_id
    db.delete(milestone)
    db.commit()
    return project_id


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------


def _owned_entry(db: DbSession, entry_id: int, *, user: User) -> ProjectEntry | None:
    entry = db.get(ProjectEntry, entry_id)
    if entry is None:
        return None
    project = db.get(Project, entry.project_id)
    if project is None or project.user_id != user.id:
        return None
    return entry


def add_entry(
    db: DbSession,
    *,
    project_id: int,
    user: User,
    entry_date: date,
    note: str,
    link: str | None,
) -> ProjectEntry | None:
    project = get_project(db, project_id, user=user)
    if project is None:
        return None
    entry = ProjectEntry(
        project_id=project_id,
        entry_date=entry_date,
        note=note.strip(),
        link=link.strip() if link else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: DbSession, entry_id: int, *, user: User) -> int | None:
    """Delete a journal entry; returns its project_id (for redirect) or None."""
    entry = _owned_entry(db, entry_id, user=user)
    if entry is None:
        return None
    project_id = entry.project_id
    db.delete(entry)
    db.commit()
    return project_id
