"""Lunch planning module integration tests."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.family_member.models import FamilyMember
from family_assistant.lunch_plan.models import LunchPlanEntry
from family_assistant.meal_plan.models import Recipe
from family_assistant.meal_plan.services import create_recipe


def test_lunch_plan_requires_auth(client: TestClient) -> None:
    response = client.get("/lunch-plan", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_lunch_plan_renders_empty_state_for_authenticated_user(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/lunch-plan")
    assert response.status_code == 200
    assert b"Lunch plan" in response.content
    assert b"Add family members first" in response.content


def test_create_lunch_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes="No peanuts", school_days=["monday", "tuesday"])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.post(
        "/lunch-plan",
        data={
            "family_member_id": str(member.id),
            "date": "2026-05-18",
            "items_text": "Turkey sandwich: no mayo\nApple slices",
            "notes": "Ice pack in side pocket",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    entry = db_session.scalars(select(LunchPlanEntry)).one()
    assert entry.family_member_id == member.id
    assert entry.date == date(2026, 5, 18)
    assert entry.items == [
        {"name": "Turkey sandwich", "notes": "no mayo"},
        {"name": "Apple slices"},
    ]
    assert entry.notes == "Ice pack in side pocket"
    assert entry.packed_status == "planned"
    assert entry.created_by_user_id == seeded_user.id


def test_create_requires_item(authenticated_client: TestClient, db_session: Session) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.post(
        "/lunch-plan",
        data={
            "family_member_id": str(member.id),
            "date": "2026-05-18",
            "items_text": " \n",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"At least one lunch item is required" in response.content


def test_update_missing_lunch_plan_entry_redirects_without_writing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    # Regression: POST to a deleted/non-existent ID used to call update_lunch_plan_entry
    # (which returns None) and then redirect 303 as if the edit succeeded.
    member = FamilyMember(name="Ghost", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()
    response = authenticated_client.post(
        "/lunch-plan/99999",
        data={
            "family_member_id": str(member.id),
            "date": "2026-05-18",
            "items_text": "Sandwich",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/lunch-plan"
    assert db_session.scalars(select(LunchPlanEntry)).all() == []


def test_update_lunch_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    other_member = FamilyMember(name="Maya", notes=None, school_days=["tuesday"])
    db_session.add_all([member, other_member])
    db_session.commit()

    entry = LunchPlanEntry(
        family_member_id=member.id,
        date=date(2026, 5, 18),
        items=[{"name": "Sandwich"}],
        notes=None,
        packed_status="packed",
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/lunch-plan/{entry.id}",
        data={
            "family_member_id": str(other_member.id),
            "date": "2026-05-19",
            "items_text": "Pasta salad\nBerry cup",
            "notes": "Use the blue container",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db_session.refresh(entry)
    assert entry.family_member_id == other_member.id
    assert entry.date == date(2026, 5, 19)
    assert entry.items == [{"name": "Pasta salad"}, {"name": "Berry cup"}]
    assert entry.notes == "Use the blue container"
    # Form no longer touches packed_status — pre-existing value preserved.
    assert entry.packed_status == "packed"


def test_mark_lunch_packed(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    entry = LunchPlanEntry(
        family_member_id=member.id,
        date=date(2026, 5, 18),
        items=[{"name": "Wrap"}],
        notes=None,
        packed_status="planned",
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/lunch-plan/{entry.id}/status",
        data={"packed_status": "packed"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(entry)
    assert entry.packed_status == "packed"


def test_mark_lunch_planned_undoes_packed(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    entry = LunchPlanEntry(
        family_member_id=member.id,
        date=date(2026, 5, 18),
        items=[{"name": "Wrap"}],
        notes=None,
        packed_status="packed",
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/lunch-plan/{entry.id}/status",
        data={"packed_status": "planned"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(entry)
    assert entry.packed_status == "planned"


def test_set_status_rejects_unknown_value(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    entry = LunchPlanEntry(
        family_member_id=member.id,
        date=date(2026, 5, 18),
        items=[{"name": "Wrap"}],
        notes=None,
        packed_status="planned",
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = authenticated_client.post(
        f"/lunch-plan/{entry.id}/status",
        data={"packed_status": "bogus"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(entry)
    assert entry.packed_status == "planned"


def test_delete_lunch_plan_entry(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    entry = LunchPlanEntry(
        family_member_id=member.id,
        date=date(2026, 5, 18),
        items=[{"name": "Wrap"}],
        notes=None,
        packed_status="planned",
        created_by_user_id=seeded_user.id,
    )
    db_session.add(entry)
    db_session.commit()
    entry_id = entry.id

    response = authenticated_client.post(f"/lunch-plan/{entry_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(LunchPlanEntry, entry_id) is None


# Week of Mon 2026-05-18 → Sun 2026-05-24. Used for school-day filter tests.
_WEEK_START = "2026-05-18"


def test_lunch_grid_only_shows_school_days(
    authenticated_client: TestClient, db_session: Session
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday", "wednesday"])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.get(f"/lunch-plan?week_start={_WEEK_START}")
    assert response.status_code == 200
    body = response.content
    assert b"May 18" in body  # Monday
    assert b"May 20" in body  # Wednesday
    assert b"May 19" not in body  # Tuesday
    assert b"May 21" not in body  # Thursday
    assert b"May 22" not in body  # Friday
    assert b"May 23" not in body  # Saturday
    assert b"May 24" not in body  # Sunday


def test_lunch_grid_includes_days_with_existing_entries(
    authenticated_client: TestClient, db_session: Session, seeded_user
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()
    # One-off lunch on Thursday, not in school_days — should still appear.
    db_session.add(
        LunchPlanEntry(
            family_member_id=member.id,
            date=date(2026, 5, 21),
            items=[{"name": "Field trip lunch"}],
            notes=None,
            packed_status="planned",
            created_by_user_id=seeded_user.id,
        )
    )
    db_session.commit()

    response = authenticated_client.get(f"/lunch-plan?week_start={_WEEK_START}")
    assert response.status_code == 200
    body = response.content
    assert b"May 18" in body  # Monday (school day)
    assert b"May 21" in body  # Thursday (has entry)
    assert b"Field trip lunch" in body
    assert b"May 19" not in body  # Tuesday (no school, no entry)


def test_new_lunch_form_shows_empty_state_when_no_family_members(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/lunch-plan/new")
    assert response.status_code == 200
    assert b"You need a family member before you can plan a lunch" in response.content
    assert b'name="items_text"' not in response.content


def test_new_lunch_form_auto_picks_only_family_member(
    authenticated_client: TestClient, db_session: Session
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.get("/lunch-plan/new")
    assert response.status_code == 200
    body = response.content
    # The selector is hidden (no <select>) and the only member's name is shown read-only.
    assert b"<select" not in body
    assert (
        b'<input type="hidden" name="family_member_id" value="' + str(member.id).encode() + b'"'
        in body
    )
    assert b"Lila" in body


def test_lunch_grid_shows_hint_when_no_school_days_configured(
    authenticated_client: TestClient, db_session: Session
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=[])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.get(f"/lunch-plan?week_start={_WEEK_START}")
    assert response.status_code == 200
    body = response.content
    assert b"No school days configured for Lila" in body
    assert b"May 18" not in body  # No day cards rendered for this member


# ---------------------------------------------------------------------------
# Lunch catalog (lunch components in the recipes table) UI
# ---------------------------------------------------------------------------


def test_lunch_catalog_list_renders(authenticated_client: TestClient, db_session: Session) -> None:
    create_recipe(db_session, name="Grilled Cheese", meal_type="lunch", ingredients=["bread"])
    response = authenticated_client.get("/lunch-plan/catalog")
    assert response.status_code == 200
    assert b"Lunch catalog" in response.content
    assert b"Grilled Cheese" in response.content


def test_lunch_catalog_create_forces_lunch_meal_type(
    authenticated_client: TestClient, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/lunch-plan/catalog",
        data={
            "name": "Apple",
            "ingredients": "apple",
            "notes": "Fruit",
            "calories": "95",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    recipe = db_session.scalars(select(Recipe)).one()
    assert recipe.name == "Apple"
    assert recipe.meal_type == "lunch"
    assert recipe.notes == "Fruit"
    assert recipe.calories == 95


def test_lunch_catalog_create_requires_name(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/lunch-plan/catalog", data={"name": "  "}, follow_redirects=False
    )
    assert response.status_code == 400
    assert b"Name is required" in response.content


def test_lunch_catalog_duplicate_name_conflicts(
    authenticated_client: TestClient, db_session: Session
) -> None:
    create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    response = authenticated_client.post(
        "/lunch-plan/catalog", data={"name": "Apple"}, follow_redirects=False
    )
    assert response.status_code == 409
    assert b"already exists" in response.content


def test_lunch_catalog_update_and_delete(
    authenticated_client: TestClient, db_session: Session
) -> None:
    recipe = create_recipe(db_session, name="Apple", meal_type="lunch", ingredients=["apple"])
    update = authenticated_client.post(
        f"/lunch-plan/catalog/{recipe.id}",
        data={"name": "Green Apple", "notes": "Fruit"},
        follow_redirects=False,
    )
    assert update.status_code == 303
    db_session.expire_all()
    assert db_session.get(Recipe, recipe.id).name == "Green Apple"

    delete = authenticated_client.post(
        f"/lunch-plan/catalog/{recipe.id}/delete", follow_redirects=False
    )
    assert delete.status_code == 303
    assert db_session.get(Recipe, recipe.id) is None


def test_lunch_form_offers_component_picker(
    authenticated_client: TestClient, db_session: Session
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()
    create_recipe(db_session, name="Grilled Cheese", meal_type="lunch", ingredients=["bread"])

    response = authenticated_client.get("/lunch-plan/new")
    assert response.status_code == 200
    assert b"Pick from catalog" in response.content
    assert b"Grilled Cheese" in response.content
