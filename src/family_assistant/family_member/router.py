"""FamilyMember router (PRD Section 10.3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.db import get_session
from family_assistant.family_member.services import (
    FamilyMemberInUseError,
    create_family_member,
    delete_family_member,
    get_family_member,
    list_family_members,
    update_family_member,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/family",
    tags=["family"],
    dependencies=[Depends(require_user)],
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    members = list_family_members(db)
    return templates.TemplateResponse(
        request,
        "family_member/list.html",
        {"members": members, "weekdays": WEEKDAYS},
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "family_member/form.html",
        {"member": None, "weekdays": WEEKDAYS, "error": None},
    )


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    school_days: Annotated[list[str] | None, Form()] = None,
) -> Response:
    if not name.strip():
        return templates.TemplateResponse(
            request,
            "family_member/form.html",
            {"member": None, "weekdays": WEEKDAYS, "error": "Name is required."},
            status_code=400,
        )
    valid_days = [d for d in (school_days or []) if d in WEEKDAYS]
    create_family_member(db, name=name, notes=notes, school_days=valid_days)
    return RedirectResponse(url="/family", status_code=303)


@router.get("/{member_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    member_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    member = get_family_member(db, member_id)
    if member is None:
        return RedirectResponse(url="/family", status_code=303)
    return templates.TemplateResponse(
        request,
        "family_member/form.html",
        {"member": member, "weekdays": WEEKDAYS, "error": None},
    )


@router.post("/{member_id}")
def update_view(
    request: Request,
    member_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    school_days: Annotated[list[str] | None, Form()] = None,
) -> Response:
    # Row deleted between GET and POST (stale tab, another device). Mirror the
    # GET edit_form behavior rather than silently no-op the update.
    if get_family_member(db, member_id) is None:
        return RedirectResponse(url="/family", status_code=303)
    if not name.strip():
        member = get_family_member(db, member_id)
        return templates.TemplateResponse(
            request,
            "family_member/form.html",
            {"member": member, "weekdays": WEEKDAYS, "error": "Name is required."},
            status_code=400,
        )
    valid_days = [d for d in (school_days or []) if d in WEEKDAYS]
    update_family_member(db, member_id=member_id, name=name, notes=notes, school_days=valid_days)
    return RedirectResponse(url="/family", status_code=303)


@router.post("/{member_id}/delete")
def delete_view(
    request: Request,
    member_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    try:
        delete_family_member(db, member_id)
    except FamilyMemberInUseError as exc:
        member = get_family_member(db, member_id)
        return templates.TemplateResponse(
            request,
            "family_member/form.html",
            {"member": member, "weekdays": WEEKDAYS, "error": str(exc)},
            status_code=409,
        )
    return RedirectResponse(url="/family", status_code=303)
