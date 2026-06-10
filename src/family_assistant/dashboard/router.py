"""Dashboard router (PRD Section 10.8)."""

from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.services import list_recent_interactions
from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.family_member.models import FamilyMember
from family_assistant.grocery.services import (
    create_grocery_item,
    find_open_item_with_name,
    list_open_items,
)
from family_assistant.household_task.services import (
    complete_task,
    get_task,
    list_active_tasks,
)
from family_assistant.lunch_plan.models import LunchPlanEntry
from family_assistant.lunch_plan.services import (
    list_family_members,
    start_of_week,
)
from family_assistant.lunch_plan.services import (
    list_week_entries as list_lunch_week_entries,
)
from family_assistant.meal_plan.services import list_entries_for_date
from family_assistant.templating import templates

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_user)],
)


def _lunch_summary(
    members: list[FamilyMember], entries: list[LunchPlanEntry]
) -> list[dict[str, object]]:
    by_member: dict[int, list[LunchPlanEntry]] = defaultdict(list)
    for entry in entries:
        by_member[entry.family_member_id].append(entry)
    summary = []
    for member in members:
        member_entries = sorted(by_member[member.id], key=lambda e: e.date)
        summary.append(
            {
                "member": member,
                "total": len(member_entries),
                "entries": member_entries,
            }
        )
    return summary


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    today = date.today()
    week_start = start_of_week(today)
    open_items = list_open_items(db)
    # Active tasks come back due-soonest-first; anything due on or before today
    # is something to do now (overdue floats to the top).
    due_tasks = [t for t in list_active_tasks(db) if t.next_due_date <= today]
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "today": today,
            "todays_meals": list_entries_for_date(db, day=today),
            "due_tasks": due_tasks,
            "lunch_summary": _lunch_summary(
                list_family_members(db),
                list_lunch_week_entries(db, week_start=week_start),
            ),
            "week_start": week_start,
            "open_items": open_items,
            "open_count": len(open_items),
            "recent_interactions": list_recent_interactions(db, user_id=user.id, limit=5),
        },
    )


@router.post("/grocery/quick-add")
def quick_add_grocery(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
) -> Response:
    cleaned = name.strip()
    if cleaned and find_open_item_with_name(db, cleaned) is None:
        create_grocery_item(
            db,
            user=user,
            name=cleaned,
            category=None,
            quantity=None,
            unit=None,
            notes=None,
        )
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/tasks/{task_id}/done")
def complete_due_task(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[DbSession, Depends(get_session)],
    task_id: int,
) -> Response:
    task = get_task(db, task_id)
    if task is not None and task.active:
        complete_task(db, task=task, user=user)
    return RedirectResponse(url="/dashboard", status_code=303)
