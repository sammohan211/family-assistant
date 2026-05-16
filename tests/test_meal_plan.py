"""Meal planning module integration tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.meal_plan.models import MealPlanEntry


def test_meal_plan_requires_auth(client: TestClient) -> None:
    response = client.get("/meal-plan", follow_redirects=False)
    assert response.status_code == 401


def test_meal_plan_list_renders_for_authenticated_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/meal-plan")
    assert response.status_code == 200
    assert b"Meal plan" in response.content
    assert b"Nothing planned" in response.content


def test_create_meal_plan_entry(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/meal-plan",
        data={
            "date": "2026-05-18",
            "meal_type": "dinner",
            "title": "Pasta night",
            "notes": "Use the spinach sauce",
            "is_favorite": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    entry = db_session.scalars(select(MealPlanEntry)).one()
    assert entry.title == "Pasta night"
    assert entry.meal_type == "dinner"
    assert entry.date == date(2026, 5, 18)
    assert entry.notes == "Use the spinach sauce"
    assert entry.is_favorite is True


def test_create_requires_title(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/meal-plan",
        data={"date": "2026-05-18", "meal_type": "dinner", "title": "   "},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Title is required" in response.content


def test_create_rejects_invalid_meal_type(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/meal-plan",
        data={"date": "2026-05-18", "meal_type": "brunch", "title": "Waffles"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Meal type is required" in response.content


def test_update_meal_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = MealPlanEntry(
        date=date(2026, 5, 18),
        meal_type="dinner",
        title="Pasta night",
        notes=None,
        is_favorite=False,
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/meal-plan/{entry.id}",
        data={
            "date": "2026-05-19",
            "meal_type": "lunch",
            "title": "Soup and toast",
            "notes": "Leftovers are fine",
            "is_favorite": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(entry)
    assert entry.date == date(2026, 5, 19)
    assert entry.meal_type == "lunch"
    assert entry.title == "Soup and toast"
    assert entry.notes == "Leftovers are fine"
    assert entry.is_favorite is True


def test_duplicate_meal_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = MealPlanEntry(
        date=date(2026, 5, 18),
        meal_type="dinner",
        title="Tacos",
        notes="Use the salsa verde",
        is_favorite=True,
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/meal-plan/{entry.id}/duplicate",
        data={"date": "2026-05-21"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    entries = db_session.scalars(select(MealPlanEntry).order_by(MealPlanEntry.id)).all()
    assert len(entries) == 2
    assert entries[1].title == "Tacos"
    assert entries[1].date == date(2026, 5, 21)
    assert entries[1].is_favorite is True


def test_duplicate_with_invalid_date_returns_400(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = MealPlanEntry(
        date=date(2026, 5, 18),
        meal_type="dinner",
        title="Tacos",
        notes=None,
        is_favorite=False,
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/meal-plan/{entry.id}/duplicate",
        data={"date": "not-a-date"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Date must be in YYYY-MM-DD format" in response.content


def test_delete_meal_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    entry = MealPlanEntry(
        date=date(2026, 5, 18),
        meal_type="dinner",
        title="Pizza",
        notes=None,
        is_favorite=False,
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()
    entry_id = entry.id

    response = authenticated_client.post(f"/meal-plan/{entry_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(MealPlanEntry, entry_id) is None
