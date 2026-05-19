"""Grocery module integration tests."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.grocery.models import GroceryItem
from family_assistant.grocery.services import list_recent_items


def test_grocery_list_requires_auth(client: TestClient) -> None:
    response = client.get("/grocery", follow_redirects=False)
    assert response.status_code == 401


def test_grocery_list_renders_for_authenticated_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/grocery")
    assert response.status_code == 200
    assert b"Grocery list" in response.content
    assert b"No open grocery items" in response.content


def test_create_grocery_item(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/grocery",
        data={
            "name": "Milk",
            "category": "dairy",
            "quantity": "2",
            "unit": "cartons",
            "notes": "2%",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    item = db_session.scalars(select(GroceryItem)).one()
    assert item.name == "Milk"
    assert item.category == "dairy"
    assert item.quantity == 2
    assert item.unit == "cartons"
    assert item.status == "open"
    assert item.notes == "2%"
    assert item.purchased_by_user_id is None


def test_create_requires_name(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/grocery",
        data={"name": "   ", "quantity": "", "unit": "", "category": "", "notes": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Name is required" in response.content


def test_create_rejects_non_numeric_quantity(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/grocery",
        data={"name": "Milk", "quantity": "two"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Quantity must be a number" in response.content


def test_create_accepts_decimal_quantity(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/grocery",
        data={"name": "Butter", "quantity": "1.5", "unit": "lb"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    item = db_session.scalars(select(GroceryItem).where(GroceryItem.name == "Butter")).one()
    assert item.quantity == Decimal("1.5")
    assert item.unit == "lb"


def test_mark_item_purchased(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    item = GroceryItem(name="Apples", added_by_user_id=seeded_user.id, status="open")
    db_session.add(item)
    db_session.commit()

    response = authenticated_client.post(f"/grocery/{item.id}/purchase", follow_redirects=False)
    assert response.status_code == 303
    db_session.refresh(item)
    assert item.status == "purchased"
    assert item.purchased_by_user_id == seeded_user.id


def test_restore_item(authenticated_client: TestClient, db_session: Session, seeded_user) -> None:
    item = GroceryItem(
        name="Bread",
        added_by_user_id=seeded_user.id,
        status="purchased",
        purchased_by_user_id=seeded_user.id,
    )
    db_session.add(item)
    db_session.commit()

    response = authenticated_client.post(f"/grocery/{item.id}/restore", follow_redirects=False)
    assert response.status_code == 303
    db_session.refresh(item)
    assert item.status == "open"
    assert item.purchased_by_user_id is None


def test_clone_item_creates_new_open_item(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    item = GroceryItem(
        name="Yogurt",
        category="dairy",
        quantity=6,
        unit="cups",
        notes="vanilla",
        added_by_user_id=seeded_user.id,
        status="purchased",
        purchased_by_user_id=seeded_user.id,
    )
    db_session.add(item)
    db_session.commit()

    response = authenticated_client.post(f"/grocery/{item.id}/clone", follow_redirects=False)
    assert response.status_code == 303

    items = db_session.scalars(select(GroceryItem).order_by(GroceryItem.id)).all()
    assert len(items) == 2
    assert items[1].name == "Yogurt"
    assert items[1].status == "open"
    assert items[1].purchased_by_user_id is None


def test_update_item(authenticated_client: TestClient, db_session: Session, seeded_user) -> None:
    item = GroceryItem(name="Eggs", added_by_user_id=seeded_user.id, status="open")
    db_session.add(item)
    db_session.commit()

    response = authenticated_client.post(
        f"/grocery/{item.id}",
        data={
            "name": "Large eggs",
            "category": "dairy",
            "quantity": "12",
            "unit": "count",
            "notes": "free range",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(item)
    assert item.name == "Large eggs"
    assert item.category == "dairy"
    assert item.quantity == 12
    assert item.unit == "count"
    assert item.notes == "free range"


def test_delete_item(authenticated_client: TestClient, db_session: Session, seeded_user) -> None:
    item = GroceryItem(name="Cheese", added_by_user_id=seeded_user.id, status="open")
    db_session.add(item)
    db_session.commit()
    item_id = item.id

    response = authenticated_client.post(f"/grocery/{item_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(GroceryItem, item_id) is None


def test_list_recent_items_dedupes_by_name_only(db_session: Session, seeded_user) -> None:
    # Same name + different quantity/unit/notes should collapse to one quick-add chip.
    db_session.add_all(
        [
            GroceryItem(name="Milk", quantity=1, unit="carton", added_by_user_id=seeded_user.id),
            GroceryItem(name="Milk", quantity=2, unit="cartons", added_by_user_id=seeded_user.id),
            GroceryItem(name="Bread", added_by_user_id=seeded_user.id),
        ]
    )
    db_session.commit()

    recent = list_recent_items(db_session)
    names = [item.name for item in recent]
    assert names.count("Milk") == 1
    assert "Bread" in names


def test_list_recent_items_keeps_most_recent_per_name(db_session: Session, seeded_user) -> None:
    older = GroceryItem(name="Yogurt", quantity=1, unit="cup", added_by_user_id=seeded_user.id)
    db_session.add(older)
    db_session.commit()
    newer = GroceryItem(name="Yogurt", quantity=4, unit="cups", added_by_user_id=seeded_user.id)
    db_session.add(newer)
    db_session.commit()

    recent = list_recent_items(db_session)
    yogurts = [item for item in recent if item.name == "Yogurt"]
    assert len(yogurts) == 1
    assert yogurts[0].id == newer.id


def test_list_recent_items_dedupes_case_insensitively(db_session: Session, seeded_user) -> None:
    db_session.add_all(
        [
            GroceryItem(name="Apples", added_by_user_id=seeded_user.id),
            GroceryItem(name="apples", added_by_user_id=seeded_user.id),
            GroceryItem(name="APPLES", added_by_user_id=seeded_user.id),
        ]
    )
    db_session.commit()

    recent = list_recent_items(db_session)
    apples = [item for item in recent if item.name.lower() == "apples"]
    assert len(apples) == 1


def test_list_recent_items_respects_limit(db_session: Session, seeded_user) -> None:
    for n in range(15):
        db_session.add(GroceryItem(name=f"Item {n}", added_by_user_id=seeded_user.id))
    db_session.commit()

    recent = list_recent_items(db_session, limit=5)
    assert len(recent) == 5
