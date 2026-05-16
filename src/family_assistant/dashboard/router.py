"""Dashboard router (PRD Section 10.8)."""

from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.family_member.models import FamilyMember
from family_assistant.grocery.services import create_grocery_item, list_open_items
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
        packed = sum(1 for e in member_entries if e.packed_status == "packed")
        summary.append(
            {
                "member": member,
                "total": len(member_entries),
                "packed": packed,
                "planned": len(member_entries) - packed,
                "entries": member_entries,
            }
        )
    return summary


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    today = date.today()
    week_start = start_of_week(today)
    open_items = list_open_items(db)
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "today": today,
            "todays_meals": list_entries_for_date(db, day=today),
            "lunch_summary": _lunch_summary(
                list_family_members(db),
                list_lunch_week_entries(db, week_start=week_start),
            ),
            "week_start": week_start,
            "open_items": open_items,
            "open_count": len(open_items),
        },
    )


@router.post("/grocery/quick-add")
def quick_add_grocery(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
) -> Response:
    if name.strip():
        create_grocery_item(
            db,
            user=user,
            name=name,
            category=None,
            quantity=None,
            unit=None,
            notes=None,
        )
    return RedirectResponse(url="/dashboard", status_code=303)
