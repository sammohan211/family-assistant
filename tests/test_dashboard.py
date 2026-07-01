"""Dashboard integration tests."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.family_member.models import FamilyMember
from family_assistant.grocery.models import GroceryItem
from family_assistant.lunch_plan.models import LunchPlanEntry
from family_assistant.lunch_plan.services import start_of_week
from family_assistant.meal_plan.models import MealPlanEntry


def test_dashboard_requires_auth(client: TestClient) -> None:
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_dashboard_renders_empty_state(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    body = response.content
    assert b"Dashboard" in body
    assert b"Nothing planned for today" in body
    assert b"No open items" in body
    assert b"No family members yet" in body


def test_dashboard_shows_todays_meals(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    today = date.today()
    db_session.add_all(
        [
            MealPlanEntry(
                date=today,
                meal_type="dinner",
                title="Pasta night",
                notes=None,
                is_favorite=False,
                created_by_user_id=seeded_user.id,
            ),
            MealPlanEntry(
                date=today + timedelta(days=1),
                meal_type="dinner",
                title="Tomorrow's tacos",
                notes=None,
                is_favorite=False,
                created_by_user_id=seeded_user.id,
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    body = response.content
    assert b"Pasta night" in body
    assert b"Tomorrow's tacos" not in body


def test_dashboard_shows_lunch_summary_per_kid(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()
    week_start = start_of_week(date.today())
    db_session.add_all(
        [
            LunchPlanEntry(
                family_member_id=member.id,
                date=week_start,
                items=[{"name": "Sandwich"}],
                notes=None,
                packed_status="planned",
                created_by_user_id=seeded_user.id,
            ),
            LunchPlanEntry(
                family_member_id=member.id,
                date=week_start + timedelta(days=1),
                items=[{"name": "Wrap"}],
                notes=None,
                packed_status="planned",
                created_by_user_id=seeded_user.id,
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    body = response.content
    assert b"Lila" in body
    assert b"2 planned" in body
    # Packed/planned distinction is dropped — should not appear.
    assert b"packed" not in body


def test_dashboard_shows_open_grocery_count_and_items(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    db_session.add_all(
        [
            GroceryItem(name="Milk", added_by_user_id=seeded_user.id),
            GroceryItem(name="Eggs", added_by_user_id=seeded_user.id),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    body = response.content
    assert b"2 open" in body
    assert b"Milk" in body
    assert b"Eggs" in body


def test_dashboard_quick_add_grocery(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/dashboard/grocery/quick-add",
        data={"name": "Bananas"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    items = db_session.scalars(select(GroceryItem)).all()
    assert len(items) == 1
    assert items[0].name == "Bananas"
    assert items[0].status == "open"


def test_dashboard_quick_add_ignores_blank(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/dashboard/grocery/quick-add",
        data={"name": "   "},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_dashboard_quick_add_silently_skips_open_duplicate(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    db_session.add(GroceryItem(name="Eggs", added_by_user_id=seeded_user.id))
    db_session.commit()

    response = authenticated_client.post(
        "/dashboard/grocery/quick-add",
        data={"name": "eggs"},  # case-insensitive match
        follow_redirects=False,
    )
    assert response.status_code == 303
    # No second row created.
    items = db_session.scalars(select(GroceryItem)).all()
    assert len(items) == 1
    assert items[0].name == "Eggs"


def test_root_redirects_authenticated_user_to_dashboard(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
