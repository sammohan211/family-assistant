"""Meal planning module integration tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.meal_plan.models import MealPlanEntry, Recipe
from family_assistant.meal_plan.services import create_recipe


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


def test_update_missing_meal_plan_entry_redirects_without_writing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    # Regression: POST to a deleted/non-existent ID used to call update_meal_plan_entry
    # (which returns None) and then redirect 303 as if the edit succeeded.
    response = authenticated_client.post(
        "/meal-plan/99999",
        data={
            "date": "2026-05-18",
            "meal_type": "dinner",
            "title": "Ghost dinner",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/meal-plan"
    assert db_session.scalars(select(MealPlanEntry)).all() == []


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


# ---------------------------------------------------------------------------
# Meal catalog (recipes) UI
# ---------------------------------------------------------------------------


def test_meal_catalog_list_renders(authenticated_client: TestClient, db_session: Session) -> None:
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    response = authenticated_client.get("/meal-plan/catalog")
    assert response.status_code == 200
    assert b"Meal catalog" in response.content
    assert b"Egg Tacos" in response.content


def test_meal_catalog_list_excludes_lunch_components(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    response = authenticated_client.get("/meal-plan/catalog")
    assert b"Apple" not in response.content


def test_meal_catalog_create(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/meal-plan/catalog",
        data={
            "name": "Butter Chicken & Rice",
            "meal_type": "dinner",
            "ingredients": "chicken breast\nrice\nbutter chicken sauce",
            "instructions": "Simmer chicken in sauce, serve over rice.",
            "calories": "650",
            "protein_g": "38",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    recipe = db_session.scalars(select(Recipe)).one()
    assert recipe.name == "Butter Chicken & Rice"
    assert recipe.ingredients == ["chicken breast", "rice", "butter chicken sauce"]
    assert recipe.instructions == "Simmer chicken in sauce, serve over rice."
    assert recipe.calories == 650
    assert recipe.protein_g == 38


def test_meal_catalog_create_requires_name(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/meal-plan/catalog",
        data={"name": "   ", "meal_type": "dinner"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Name is required" in response.content


def test_meal_catalog_create_rejects_lunch_meal_type(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/meal-plan/catalog",
        data={"name": "Sneaky", "meal_type": "lunch"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Meal type must be one of" in response.content


def test_meal_catalog_create_rejects_bad_calories(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/meal-plan/catalog",
        data={"name": "X", "meal_type": "dinner", "calories": "lots"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Calories must be a whole number" in response.content


def test_meal_catalog_duplicate_name_conflicts(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    response = authenticated_client.post(
        "/meal-plan/catalog",
        data={"name": "Egg Tacos", "meal_type": "dinner"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert b"already exists" in response.content


def test_meal_catalog_update(authenticated_client: TestClient, db_session: Session) -> None:
    recipe = create_recipe(db_session, name="Tacos", meal_type="dinner", ingredients=["eggs"])
    response = authenticated_client.post(
        f"/meal-plan/catalog/{recipe.id}",
        data={
            "name": "Egg Tacos",
            "meal_type": "dinner",
            "ingredients": "eggs\ncheese",
            "instructions": "Cook.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(Recipe, recipe.id)
    assert refreshed.name == "Egg Tacos"
    assert refreshed.ingredients == ["eggs", "cheese"]
    assert refreshed.instructions == "Cook."


def test_meal_catalog_delete(authenticated_client: TestClient, db_session: Session) -> None:
    recipe = create_recipe(db_session, name="Tacos", meal_type="dinner", ingredients=["eggs"])
    response = authenticated_client.post(
        f"/meal-plan/catalog/{recipe.id}/delete", follow_redirects=False
    )
    assert response.status_code == 303
    assert db_session.get(Recipe, recipe.id) is None


def test_meal_form_offers_catalog_picker(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_recipe(db_session, name="Egg Tacos", meal_type="dinner", ingredients=["eggs"])
    response = authenticated_client.get("/meal-plan/new")
    assert response.status_code == 200
    assert b"Pick from catalog" in response.content
    assert b"Egg Tacos" in response.content
