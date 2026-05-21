"""Memory CRUD router (PRD Section 11.7)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.family_member.models import FamilyMember
from family_assistant.memory.models import Memory
from family_assistant.memory.services import (
    MEMORY_TYPES,
    SUBJECT_TYPES,
    MemoryConfirmationRequiredError,
    create_memory,
    delete_memory,
    format_tags,
    get_memory,
    list_memories,
    parse_tags,
    update_memory,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/memory",
    tags=["memory"],
    dependencies=[Depends(require_user)],
)


def _all_users(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.name)).all())


def _all_family_members(db: DbSession) -> list[FamilyMember]:
    return list(db.scalars(select(FamilyMember).order_by(FamilyMember.name)).all())


def _subjects_map(
    users: list[User], family_members: list[FamilyMember]
) -> dict[tuple[str, int | None], str]:
    mapping: dict[tuple[str, int | None], str] = {("household", None): "Household"}
    for user in users:
        mapping[("user", user.id)] = user.name
        mapping[("user", None)] = mapping.get(("user", None), "User")
    for member in family_members:
        mapping[("family_member", member.id)] = member.name
        mapping[("family_member", None)] = mapping.get(("family_member", None), "Family member")
    return mapping


def _subject_label(
    subjects_map: dict[tuple[str, int | None], str], subject_type: str, subject_id: int | None
) -> str:
    return subjects_map.get(
        (subject_type, subject_id),
        subjects_map.get((subject_type, None), subject_type),
    )


def _resolve_subject(
    subject_type: str,
    user_subject_id: int | None,
    family_member_subject_id: int | None,
    users: list[User],
    family_members: list[FamilyMember],
) -> tuple[int | None, str | None]:
    """Returns (subject_id, error)."""
    if subject_type not in SUBJECT_TYPES:
        return None, "Choose a valid subject."
    if subject_type == "household":
        return None, None
    if subject_type == "user":
        if user_subject_id is None:
            return None, "Choose a user."
        if user_subject_id not in {u.id for u in users}:
            return None, "Unknown user."
        return user_subject_id, None
    if subject_type == "family_member":
        if family_member_subject_id is None:
            return None, "Choose a family member."
        if family_member_subject_id not in {m.id for m in family_members}:
            return None, "Unknown family member."
        return family_member_subject_id, None
    return None, "Choose a valid subject."


def _render_form(
    request: Request,
    *,
    item: Memory | None,
    users: list[User],
    family_members: list[FamilyMember],
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "memory/form.html",
        {
            "item": item,
            "users": users,
            "family_members": family_members,
            "subject_types": SUBJECT_TYPES,
            "memory_types": MEMORY_TYPES,
            "error": error,
            "form_data": form_data or {},
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    subject_type: Annotated[str | None, Query()] = None,
    subject_id: Annotated[int | None, Query()] = None,
    memory_type: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
) -> Response:
    filters = {
        "subject_type": subject_type or None,
        "subject_id": subject_id,
        "memory_type": memory_type or None,
        "query": q or None,
        "tag": tag or None,
    }
    users = _all_users(db)
    family_members = _all_family_members(db)
    memories = list_memories(db, **filters)
    subjects_map = _subjects_map(users, family_members)
    return templates.TemplateResponse(
        request,
        "memory/list.html",
        {
            "memories": memories,
            "users": users,
            "family_members": family_members,
            "subject_types": SUBJECT_TYPES,
            "memory_types": MEMORY_TYPES,
            "subjects_map": subjects_map,
            "subject_label": lambda st, sid: _subject_label(subjects_map, st, sid),
            "filters": {
                "subject_type": subject_type or "",
                "subject_id": str(subject_id) if subject_id is not None else "",
                "memory_type": memory_type or "",
                "q": q or "",
                "tag": tag or "",
            },
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    subject_type: Annotated[str | None, Query()] = None,
    subject_id: Annotated[int | None, Query()] = None,
) -> Response:
    users = _all_users(db)
    family_members = _all_family_members(db)
    initial_subject_type = subject_type if subject_type in SUBJECT_TYPES else "household"
    form_data = {
        "subject_type": initial_subject_type,
        "memory_type": "preference",
    }
    if initial_subject_type == "user" and subject_id is not None:
        form_data["user_subject_id"] = str(subject_id)
    if initial_subject_type == "family_member" and subject_id is not None:
        form_data["family_member_subject_id"] = str(subject_id)
    return _render_form(
        request,
        item=None,
        users=users,
        family_members=family_members,
        error=None,
        form_data=form_data,
    )


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    subject_type: Annotated[str, Form()],
    memory_type: Annotated[str, Form()],
    content: Annotated[str, Form()],
    user_subject_id: Annotated[int | None, Form()] = None,
    family_member_subject_id: Annotated[int | None, Form()] = None,
    is_hard_restriction: Annotated[bool, Form()] = False,
    tags: Annotated[str, Form()] = "",
) -> Response:
    users = _all_users(db)
    family_members = _all_family_members(db)
    form_data = {
        "subject_type": subject_type,
        "memory_type": memory_type,
        "content": content,
        "user_subject_id": str(user_subject_id) if user_subject_id else "",
        "family_member_subject_id": (
            str(family_member_subject_id) if family_member_subject_id else ""
        ),
        "is_hard_restriction": "on" if is_hard_restriction else "",
        "tags": tags,
    }

    if not content.strip():
        return _render_form(
            request,
            item=None,
            users=users,
            family_members=family_members,
            error="Content is required.",
            form_data=form_data,
            status_code=400,
        )
    if memory_type not in MEMORY_TYPES:
        return _render_form(
            request,
            item=None,
            users=users,
            family_members=family_members,
            error="Choose a memory type.",
            form_data=form_data,
            status_code=400,
        )
    resolved_subject_id, subject_error = _resolve_subject(
        subject_type, user_subject_id, family_member_subject_id, users, family_members
    )
    if subject_error:
        return _render_form(
            request,
            item=None,
            users=users,
            family_members=family_members,
            error=subject_error,
            form_data=form_data,
            status_code=400,
        )

    create_memory(
        db,
        user=user,
        subject_type=subject_type,
        subject_id=resolved_subject_id,
        memory_type=memory_type,
        content=content,
        is_hard_restriction=is_hard_restriction,
        tags=parse_tags(tags),
    )
    return RedirectResponse(url="/memory", status_code=303)


@router.get("/{memory_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    memory_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_memory(db, memory_id)
    if item is None:
        return RedirectResponse(url="/memory", status_code=303)
    users = _all_users(db)
    family_members = _all_family_members(db)
    form_data = {
        "subject_type": item.subject_type,
        "user_subject_id": str(item.subject_id) if item.subject_type == "user" else "",
        "family_member_subject_id": (
            str(item.subject_id) if item.subject_type == "family_member" else ""
        ),
        "memory_type": item.memory_type,
        "content": item.content,
        "is_hard_restriction": "on" if item.is_hard_restriction else "",
        "tags": format_tags(item.tags),
    }
    return _render_form(
        request,
        item=item,
        users=users,
        family_members=family_members,
        error=None,
        form_data=form_data,
    )


@router.post("/{memory_id}")
def update_view(
    request: Request,
    memory_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    subject_type: Annotated[str, Form()],
    memory_type: Annotated[str, Form()],
    content: Annotated[str, Form()],
    user_subject_id: Annotated[int | None, Form()] = None,
    family_member_subject_id: Annotated[int | None, Form()] = None,
    is_hard_restriction: Annotated[bool, Form()] = False,
    tags: Annotated[str, Form()] = "",
    confirm_hard_restriction: Annotated[bool, Form()] = False,
) -> Response:
    item = get_memory(db, memory_id)
    # Row deleted between GET and POST (stale tab, another device). Mirror the
    # GET edit_form behavior rather than silently no-op the update.
    if item is None:
        return RedirectResponse(url="/memory", status_code=303)
    users = _all_users(db)
    family_members = _all_family_members(db)
    form_data = {
        "subject_type": subject_type,
        "memory_type": memory_type,
        "content": content,
        "user_subject_id": str(user_subject_id) if user_subject_id else "",
        "family_member_subject_id": (
            str(family_member_subject_id) if family_member_subject_id else ""
        ),
        "is_hard_restriction": "on" if is_hard_restriction else "",
        "tags": tags,
    }

    if not content.strip():
        return _render_form(
            request,
            item=item,
            users=users,
            family_members=family_members,
            error="Content is required.",
            form_data=form_data,
            status_code=400,
        )
    if memory_type not in MEMORY_TYPES:
        return _render_form(
            request,
            item=item,
            users=users,
            family_members=family_members,
            error="Choose a memory type.",
            form_data=form_data,
            status_code=400,
        )
    resolved_subject_id, subject_error = _resolve_subject(
        subject_type, user_subject_id, family_member_subject_id, users, family_members
    )
    if subject_error:
        return _render_form(
            request,
            item=item,
            users=users,
            family_members=family_members,
            error=subject_error,
            form_data=form_data,
            status_code=400,
        )

    try:
        update_memory(
            db,
            memory_id=memory_id,
            subject_type=subject_type,
            subject_id=resolved_subject_id,
            memory_type=memory_type,
            content=content,
            is_hard_restriction=is_hard_restriction,
            tags=parse_tags(tags),
            confirmed=confirm_hard_restriction,
        )
    except MemoryConfirmationRequiredError as exc:
        return _render_form(
            request,
            item=item,
            users=users,
            family_members=family_members,
            error=str(exc),
            form_data=form_data,
            status_code=400,
        )
    return RedirectResponse(url="/memory", status_code=303)


@router.get("/{memory_id}/delete", response_class=HTMLResponse)
def delete_confirm(
    request: Request,
    memory_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_memory(db, memory_id)
    if item is None:
        return RedirectResponse(url="/memory", status_code=303)
    return templates.TemplateResponse(
        request,
        "memory/delete_confirm.html",
        {"item": item},
    )


@router.post("/{memory_id}/delete")
def delete_view(
    request: Request,
    memory_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    confirm: Annotated[str, Form()] = "",
) -> Response:
    try:
        delete_memory(db, memory_id, confirmed=(confirm == "yes"))
    except MemoryConfirmationRequiredError:
        return RedirectResponse(url=f"/memory/{memory_id}/delete", status_code=303)
    return RedirectResponse(url="/memory", status_code=303)
