"""Grocery router (PRD Section 10.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.dependencies import require_user
from family_assistant.auth.models import User
from family_assistant.db import get_session
from family_assistant.grocery.services import (
    clone_grocery_item,
    create_grocery_item,
    delete_grocery_item,
    get_grocery_item,
    list_open_items,
    list_purchased_items,
    list_recent_items,
    mark_grocery_item_purchased,
    restore_grocery_item,
    update_grocery_item,
)
from family_assistant.templating import templates

router = APIRouter(
    prefix="/grocery",
    tags=["grocery"],
    dependencies=[Depends(require_user)],
)


def _parse_quantity(value: str) -> tuple[int | None, str | None]:
    if not value.strip():
        return None, None
    try:
        parsed = int(value)
    except ValueError:
        return None, "Quantity must be a whole number."
    if parsed <= 0:
        return None, "Quantity must be greater than zero."
    return parsed, None


def _render_form(
    request: Request,
    *,
    item,
    error: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "grocery/form.html",
        {"item": item, "error": error, "form_data": form_data or {}},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    return templates.TemplateResponse(
        request,
        "grocery/list.html",
        {
            "open_items": list_open_items(db),
            "purchased_items": list_purchased_items(db),
            "recent_items": list_recent_items(db),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request) -> Response:
    return _render_form(request, item=None, error=None)


@router.post("")
def create_view(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
    name: Annotated[str, Form()],
    category: Annotated[str, Form()] = "",
    quantity: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    form_data = {
        "name": name,
        "category": category,
        "quantity": quantity,
        "unit": unit,
        "notes": notes,
    }
    if not name.strip():
        return _render_form(
            request,
            item=None,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_quantity, quantity_error = _parse_quantity(quantity)
    if quantity_error:
        return _render_form(
            request,
            item=None,
            error=quantity_error,
            form_data=form_data,
            status_code=400,
        )
    create_grocery_item(
        db,
        user=user,
        name=name,
        category=category,
        quantity=parsed_quantity,
        unit=unit,
        notes=notes,
    )
    return RedirectResponse(url="/grocery", status_code=303)


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    item = get_grocery_item(db, item_id)
    if item is None:
        return RedirectResponse(url="/grocery", status_code=303)
    return _render_form(request, item=item, error=None)


@router.post("/{item_id}")
def update_view(
    request: Request,
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    name: Annotated[str, Form()],
    category: Annotated[str, Form()] = "",
    quantity: Annotated[str, Form()] = "",
    unit: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
) -> Response:
    item = get_grocery_item(db, item_id)
    form_data = {
        "name": name,
        "category": category,
        "quantity": quantity,
        "unit": unit,
        "notes": notes,
    }
    if not name.strip():
        return _render_form(
            request,
            item=item,
            error="Name is required.",
            form_data=form_data,
            status_code=400,
        )
    parsed_quantity, quantity_error = _parse_quantity(quantity)
    if quantity_error:
        return _render_form(
            request,
            item=item,
            error=quantity_error,
            form_data=form_data,
            status_code=400,
        )
    update_grocery_item(
        db,
        item_id=item_id,
        name=name,
        category=category,
        quantity=parsed_quantity,
        unit=unit,
        notes=notes,
    )
    return RedirectResponse(url="/grocery", status_code=303)


@router.post("/{item_id}/purchase")
def purchase_view(
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    mark_grocery_item_purchased(db, item_id=item_id, user=user)
    return RedirectResponse(url="/grocery", status_code=303)


@router.post("/{item_id}/restore")
def restore_view(
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    restore_grocery_item(db, item_id=item_id)
    return RedirectResponse(url="/grocery", status_code=303)


@router.post("/{item_id}/clone")
def clone_view(
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
    user: Annotated[User, Depends(require_user)],
) -> Response:
    clone_grocery_item(db, item_id=item_id, user=user)
    return RedirectResponse(url="/grocery", status_code=303)


@router.post("/{item_id}/delete")
def delete_view(
    item_id: int,
    db: Annotated[DbSession, Depends(get_session)],
) -> Response:
    delete_grocery_item(db, item_id)
    return RedirectResponse(url="/grocery", status_code=303)
