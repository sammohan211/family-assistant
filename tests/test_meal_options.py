"""Groceries on hand (kitchen / freezer) and the "What can I make?" tab."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.ai_gateway.prompt import build_context, render_messages
from family_assistant.auth.models import User
from family_assistant.grocery.models import GroceryItem
from family_assistant.grocery.services import create_grocery_item, list_on_hand_items
from family_assistant.main import app
from family_assistant.meal_plan.models import Recipe
from family_assistant.meal_plan.options import match_recipes, validate_picks
from family_assistant.meal_plan.router import get_meal_options_llm
from family_assistant.meal_plan.services import create_recipe


class FakeLLM:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    def chat_json(self, messages: list[dict[str, str]]) -> Any:
        self.calls.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _recipe(name: str, ingredients: list[str], meal_type: str = "dinner") -> Recipe:
    return Recipe(name=name, meal_type=meal_type, ingredients=ingredients)


def _item(name: str, location: str = "kitchen") -> GroceryItem:
    return GroceryItem(name=name, status="purchased", location=location)


def _on_hand(db: Session, user: User, name: str, location: str = "kitchen") -> GroceryItem:
    return create_grocery_item(
        db,
        user=user,
        name=name,
        category=None,
        quantity=None,
        unit=None,
        notes=None,
        on_hand=True,
        location=location,
    )


# --- Matching ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [
        ("cheese", "Cheddar Cheese"),  # item more specific than ingredient
        ("chicken", "Chicken breast"),
        ("eggs", "Egg"),  # plurals
        ("tomatoes", "tomato"),
        ("Corn Tortillas", "corn tortilla"),
    ],
)
def test_ingredient_matches(ingredient: str, item: str) -> None:
    result = match_recipes([_recipe("R", [ingredient])], [_item(item)])
    assert [r["name"] for r in result["ready"]] == ["R"]


@pytest.mark.parametrize(
    ("ingredient", "item"),
    [
        ("butter chicken sauce", "Butter"),  # three-word ingredient needs all words
        ("cheese", "Cream"),
        ("chicken breast", "Chicken"),  # would also match "chicken nuggets"
        ("chicken nuggets", "Chicken"),
    ],
)
def test_ingredient_does_not_match(ingredient: str, item: str) -> None:
    result = match_recipes([_recipe("R", [ingredient, "salt"])], [_item(item), _item("Salt")])
    assert result["ready"] == []


def test_match_splits_ready_almost_and_drops_the_rest() -> None:
    recipes = [
        _recipe("Egg Tacos", ["corn tortillas", "eggs", "cheese", "salsa"]),
        _recipe("Butter Chicken & Rice", ["chicken", "butter chicken sauce", "rice"]),
        _recipe("Sheet Pan Salmon", ["salmon", "zucchini", "potato", "olive oil"]),
        _recipe("TV Dinner", []),  # no ingredients: matched by its own name
        _recipe("Order food", []),
    ]
    on_hand = [
        _item("Eggs"),
        _item("Cheddar Cheese"),
        _item("Corn tortillas"),
        _item("Salsa"),
        _item("Chicken", "freezer"),
        _item("Rice"),
        _item("TV Dinner", "freezer"),
    ]
    result = match_recipes(recipes, on_hand)

    assert [r["name"] for r in result["ready"]] == ["Egg Tacos", "TV Dinner"]
    [almost] = result["almost"]
    assert almost["name"] == "Butter Chicken & Rice"
    assert almost["missing"] == ["butter chicken sauce"]
    assert almost["from_freezer"] == ["Chicken"]


def test_validate_picks_keeps_only_matched_names() -> None:
    options = {
        "ready": [{"name": "Egg Tacos"}],
        "almost": [{"name": "Butter Chicken & Rice"}],
    }
    raw = {
        "picks": [
            {"name": "egg tacos", "reason": "Everything's here."},
            {"name": "Pizza", "reason": "invented"},
            {"name": "Egg Tacos", "reason": "duplicate"},
            {"name": "Butter Chicken & Rice", "reason": "Just need sauce."},
        ]
    }
    assert validate_picks(raw, options) == [
        {"name": "Egg Tacos", "reason": "Everything's here."},
        {"name": "Butter Chicken & Rice", "reason": "Just need sauce."},
    ]
    assert validate_picks({"nope": 1}, options) == []


# --- Grocery on-hand flow ----------------------------------------------------


def test_bought_item_is_on_hand_then_used_up(
    authenticated_client: TestClient, db_session: Session
) -> None:
    authenticated_client.post("/grocery", data={"name": "Rice"})
    item = db_session.scalars(select(GroceryItem)).one()

    authenticated_client.post(f"/grocery/{item.id}/purchase")
    db_session.refresh(item)
    assert (item.status, item.location) == ("purchased", "kitchen")
    page = authenticated_client.get("/grocery").text
    assert "In the kitchen" in page and "Rice" in page

    authenticated_client.post(f"/grocery/{item.id}/move", data={"location": "freezer"})
    db_session.refresh(item)
    assert item.location == "freezer"

    authenticated_client.post(f"/grocery/{item.id}/used-up")
    db_session.refresh(item)
    assert item.status == "used_up"
    assert list_on_hand_items(db_session) == []


def test_move_rejects_unknown_location(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    item = _on_hand(db_session, seeded_user, "Peas")
    authenticated_client.post(f"/grocery/{item.id}/move", data={"location": "garage"})
    db_session.refresh(item)
    assert item.location == "kitchen"


def test_add_straight_to_freezer_skips_duplicate_check(
    authenticated_client: TestClient, db_session: Session
) -> None:
    authenticated_client.post("/grocery", data={"name": "Peas"})
    response = authenticated_client.post(
        "/grocery", data={"name": "Peas", "where": "freezer"}, follow_redirects=False
    )
    assert response.status_code == 303
    frozen = db_session.scalars(select(GroceryItem).where(GroceryItem.status == "purchased")).one()
    assert frozen.location == "freezer"
    assert frozen.purchased_by_user_id is not None


def test_buy_again_puts_on_hand_item_back_on_list(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    item = _on_hand(db_session, seeded_user, "Milk")
    authenticated_client.post(f"/grocery/{item.id}/restore")
    db_session.refresh(item)
    assert item.status == "open"


# --- What can I make? tab ----------------------------------------------------


@pytest.fixture
def stocked(db_session: Session, seeded_user: User) -> None:
    create_recipe(
        db_session,
        name="Egg Tacos",
        meal_type="dinner",
        ingredients=["corn tortillas", "eggs", "salsa"],
        notes=None,
        calories=None,
        protein_g=None,
    )
    create_recipe(
        db_session,
        name="Butter Chicken & Rice",
        meal_type="dinner",
        ingredients=["chicken", "butter chicken sauce", "rice"],
        notes=None,
        calories=None,
        protein_g=None,
    )
    for name in ("Eggs", "Corn tortillas", "Salsa", "Rice"):
        _on_hand(db_session, seeded_user, name)
    _on_hand(db_session, seeded_user, "Chicken", "freezer")


@pytest.mark.usefixtures("stocked")
def test_options_page_lists_matches_without_calling_llm(authenticated_client: TestClient) -> None:
    llm = FakeLLM({"picks": []})
    app.dependency_overrides[get_meal_options_llm] = lambda: llm
    try:
        page = authenticated_client.get("/meal-plan/options").text
    finally:
        app.dependency_overrides.pop(get_meal_options_llm, None)
    assert llm.calls == []
    ready = page.split("Ready now")[1].split("Missing one or two")[0]
    assert "Egg Tacos" in ready
    assert "Missing: butter chicken sauce" in page
    assert "thaw Chicken" in page


@pytest.mark.usefixtures("stocked")
def test_suggest_shows_validated_picks(authenticated_client: TestClient) -> None:
    llm = FakeLLM(
        {
            "picks": [
                {"name": "Egg Tacos", "reason": "You have it all."},
                {"name": "Lasagne", "reason": "made up"},
            ]
        }
    )
    app.dependency_overrides[get_meal_options_llm] = lambda: llm
    try:
        page = authenticated_client.get("/meal-plan/options?ask=1").text
    finally:
        app.dependency_overrides.pop(get_meal_options_llm, None)
    [messages] = llm.calls
    assert "butter chicken sauce" in messages[1]["content"]
    assert "You have it all." in page
    assert "Lasagne" not in page


@pytest.mark.usefixtures("stocked")
def test_suggest_failure_still_shows_matches(authenticated_client: TestClient) -> None:
    app.dependency_overrides[get_meal_options_llm] = lambda: FakeLLM(RuntimeError("down"))
    try:
        page = authenticated_client.get("/meal-plan/options?ask=1").text
    finally:
        app.dependency_overrides.pop(get_meal_options_llm, None)
    assert "Couldn't get suggestions right now" in page
    assert "Egg Tacos" in page


@pytest.mark.usefixtures("stocked")
def test_add_missing_puts_ingredients_on_list_once(
    authenticated_client: TestClient, db_session: Session
) -> None:
    for _ in range(2):
        response = authenticated_client.post(
            "/meal-plan/options/add-missing",
            data={"recipe": "Butter Chicken & Rice"},
            follow_redirects=False,
        )
        assert response.status_code == 303
    to_buy = db_session.scalars(select(GroceryItem).where(GroceryItem.status == "open")).all()
    assert [i.name for i in to_buy] == ["butter chicken sauce"]


def test_plan_link_prefills_title(authenticated_client: TestClient) -> None:
    page = authenticated_client.get("/meal-plan/new?title=Egg%20Tacos").text
    assert 'value="Egg Tacos"' in page


# --- Chat assistant context --------------------------------------------------


def test_prompt_context_separates_to_buy_from_on_hand(
    db_session: Session, seeded_user: User
) -> None:
    create_grocery_item(
        db_session,
        user=seeded_user,
        name="Salsa",
        category=None,
        quantity=None,
        unit=None,
        notes=None,
    )
    _on_hand(db_session, seeded_user, "Eggs")
    create_recipe(
        db_session,
        name="Egg Tacos",
        meal_type="dinner",
        ingredients=["eggs", "salsa"],
        notes=None,
        calories=None,
        protein_g=None,
    )
    context = build_context(db_session, "what can I cook tonight?")
    assert [i["name"] for i in context.grocery_to_buy] == ["Salsa"]
    assert [i["name"] for i in context.on_hand] == ["Eggs"]
    assert context.recipe_matches["almost"][0]["missing"] == ["salsa"]


@pytest.mark.usefixtures("stocked")
def test_naming_a_recipe_loads_the_catalog(db_session: Session) -> None:
    context = build_context(db_session, "add stuff for egg tacos to the list")
    assert any(r["name"] == "Egg Tacos" for r in context.recipe_catalog)


def test_prompt_sends_only_the_domains_a_request_touches(db_session: Session) -> None:
    [system, _] = render_messages(build_context(db_session, "what should we cook tonight?"), "x")
    assert '"meal_plan.create_entry"' in system["content"]
    assert '"exercise.log_activity"' not in system["content"]
    assert "bench press" not in system["content"]  # exercise examples left out


def test_prompt_sends_everything_when_no_domain_matches(db_session: Session) -> None:
    [system, _] = render_messages(build_context(db_session, "hi"), "hi")
    for tool in ("grocery.add_items", "lunch_plan.create_entry", "exercise.log_activity"):
        assert f'"{tool}"' in system["content"]
