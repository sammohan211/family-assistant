"""Grocery CRUD services (PRD Section 10.4)."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.grocery.models import GroceryItem


def _with_users(statement):
    return statement.options(
        selectinload(GroceryItem.added_by_user),
        selectinload(GroceryItem.purchased_by_user),
    )


def list_open_items(db: DbSession) -> list[GroceryItem]:
    statement = (
        select(GroceryItem)
        .where(GroceryItem.status == "open")
        .order_by(GroceryItem.category.is_(None), GroceryItem.category, GroceryItem.name)
    )
    return list(db.scalars(_with_users(statement)).all())


def list_purchased_items(db: DbSession, limit: int = 20) -> list[GroceryItem]:
    statement = (
        select(GroceryItem)
        .where(GroceryItem.status == "purchased")
        .order_by(GroceryItem.updated_at.desc(), GroceryItem.id.desc())
        .limit(limit)
    )
    return list(db.scalars(_with_users(statement)).all())


def list_recent_items(db: DbSession, limit: int = 8, scan_limit: int = 200) -> list[GroceryItem]:
    """Return the N most-recently-added unique grocery items (case-insensitive name).

    Only the latest `scan_limit` rows are considered, so this stays bounded as
    history grows. At household scale that window almost always contains many
    distinct names.
    """
    statement = (
        select(GroceryItem)
        .order_by(GroceryItem.created_at.desc(), GroceryItem.id.desc())
        .limit(scan_limit)
    )
    candidates = list(db.scalars(_with_users(statement)).all())
    seen: set[str] = set()
    recent: list[GroceryItem] = []
    for item in candidates:
        key = item.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        recent.append(item)
        if len(recent) >= limit:
            break
    return recent


def get_grocery_item(db: DbSession, item_id: int) -> GroceryItem | None:
    return db.get(GroceryItem, item_id)


def create_grocery_item(
    db: DbSession,
    *,
    user: User,
    name: str,
    category: str | None,
    quantity: int | None,
    unit: str | None,
    notes: str | None,
) -> GroceryItem:
    item = GroceryItem(
        name=name.strip(),
        category=category.strip() if category else None,
        quantity=quantity,
        unit=unit.strip() if unit else None,
        notes=notes.strip() if notes else None,
        added_by_user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_grocery_item(
    db: DbSession,
    *,
    item_id: int,
    name: str,
    category: str | None,
    quantity: int | None,
    unit: str | None,
    notes: str | None,
) -> GroceryItem | None:
    item = db.get(GroceryItem, item_id)
    if item is None:
        return None
    item.name = name.strip()
    item.category = category.strip() if category else None
    item.quantity = quantity
    item.unit = unit.strip() if unit else None
    item.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(item)
    return item


def mark_grocery_item_purchased(db: DbSession, *, item_id: int, user: User) -> GroceryItem | None:
    item = db.get(GroceryItem, item_id)
    if item is None:
        return None
    item.status = "purchased"
    item.purchased_by_user_id = user.id
    db.commit()
    db.refresh(item)
    return item


def restore_grocery_item(db: DbSession, *, item_id: int) -> GroceryItem | None:
    item = db.get(GroceryItem, item_id)
    if item is None:
        return None
    item.status = "open"
    item.purchased_by_user_id = None
    db.commit()
    db.refresh(item)
    return item


def delete_grocery_item(db: DbSession, item_id: int) -> bool:
    item = db.get(GroceryItem, item_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def clone_grocery_item(db: DbSession, *, item_id: int, user: User) -> GroceryItem | None:
    item = db.get(GroceryItem, item_id)
    if item is None:
        return None
    return create_grocery_item(
        db,
        user=user,
        name=item.name,
        category=item.category,
        quantity=item.quantity,
        unit=item.unit,
        notes=item.notes,
    )
