"""Assistant router integration tests."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.ai_gateway.models import AssistantInteraction
from family_assistant.assistant.dependencies import get_llm
from family_assistant.grocery.models import GroceryItem
from family_assistant.main import app


class FakeLLM:
    def __init__(self) -> None:
        self.next_response: dict[str, Any] = {"tool_calls": [], "reply": "ok"}

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return self.next_response


@pytest.fixture
def fake_llm(authenticated_client: TestClient) -> Iterator[FakeLLM]:
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    try:
        yield llm
    finally:
        app.dependency_overrides.pop(get_llm, None)


def test_assistant_requires_auth(client: TestClient) -> None:
    response = client.get("/assistant", follow_redirects=False)
    assert response.status_code == 401


def test_assistant_get_renders_empty_state(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/assistant")
    assert response.status_code == 200
    assert b"Assistant" in response.content
    assert b"input_text" in response.content


def test_assistant_post_low_risk_executes_and_redirects(
    authenticated_client: TestClient, fake_llm: FakeLLM, db_session: Session
) -> None:
    fake_llm.next_response = {
        "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Milk"}]}}],
        "reply": "Added milk.",
    }

    response = authenticated_client.post(
        "/assistant", data={"input_text": "add milk"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/assistant"

    items = db_session.scalars(select(GroceryItem)).all()
    assert [i.name for i in items] == ["Milk"]

    interactions = db_session.scalars(select(AssistantInteraction)).all()
    assert len(interactions) == 1
    assert interactions[0].confirmation_status == "auto"


def test_assistant_post_blank_input_is_ignored(
    authenticated_client: TestClient, fake_llm: FakeLLM, db_session: Session
) -> None:
    response = authenticated_client.post(
        "/assistant", data={"input_text": "   "}, follow_redirects=False
    )
    assert response.status_code == 303
    assert db_session.scalars(select(AssistantInteraction)).all() == []


def test_assistant_get_shows_latest_and_history(
    authenticated_client: TestClient, fake_llm: FakeLLM
) -> None:
    fake_llm.next_response = {
        "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Bread"}]}}],
        "reply": "Added bread.",
    }
    authenticated_client.post("/assistant", data={"input_text": "add bread"})
    fake_llm.next_response = {"tool_calls": [], "reply": "Yes, bread is on the list."}
    authenticated_client.post("/assistant", data={"input_text": "do I have bread?"})

    response = authenticated_client.get("/assistant")
    assert response.status_code == 200
    body = response.content
    assert b"do I have bread?" in body
    assert b"add bread" in body


def test_assistant_confirmation_flow_approve(
    authenticated_client: TestClient,
    fake_llm: FakeLLM,
    db_session: Session,
) -> None:
    fake_llm.next_response = {
        "tool_calls": [
            {
                "name": "grocery.add_items",
                "args": {"items": [{"name": n} for n in ["a", "b", "c", "d", "e"]]},
            }
        ],
        "reply": "",
    }
    authenticated_client.post("/assistant", data={"input_text": "add five things"})

    pending = db_session.scalar(select(AssistantInteraction))
    assert pending is not None
    assert pending.confirmation_status == "pending_confirmation"
    assert db_session.scalars(select(GroceryItem)).all() == []

    response = authenticated_client.post(f"/assistant/{pending.id}/confirm", follow_redirects=False)
    assert response.status_code == 303

    db_session.expire_all()
    updated = db_session.get(AssistantInteraction, pending.id)
    assert updated is not None
    assert updated.confirmation_status == "approved"
    items = db_session.scalars(select(GroceryItem)).all()
    assert sorted(i.name for i in items) == ["a", "b", "c", "d", "e"]


def test_assistant_confirmation_flow_cancel(
    authenticated_client: TestClient, fake_llm: FakeLLM, db_session: Session
) -> None:
    fake_llm.next_response = {
        "tool_calls": [
            {
                "name": "grocery.add_items",
                "args": {"items": [{"name": n} for n in ["a", "b", "c", "d"]]},
            }
        ],
        "reply": "",
    }
    authenticated_client.post("/assistant", data={"input_text": "add four things"})
    pending = db_session.scalar(select(AssistantInteraction))
    assert pending is not None
    assert pending.confirmation_status == "pending_confirmation"

    response = authenticated_client.post(f"/assistant/{pending.id}/cancel", follow_redirects=False)
    assert response.status_code == 303

    db_session.expire_all()
    updated = db_session.get(AssistantInteraction, pending.id)
    assert updated is not None
    assert updated.confirmation_status == "cancelled"
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_assistant_confirm_idempotent_for_non_pending(
    authenticated_client: TestClient, fake_llm: FakeLLM, db_session: Session
) -> None:
    fake_llm.next_response = {
        "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Milk"}]}}],
        "reply": "Added milk.",
    }
    authenticated_client.post("/assistant", data={"input_text": "add milk"})
    auto = db_session.scalar(select(AssistantInteraction))
    assert auto is not None
    assert auto.confirmation_status == "auto"

    response = authenticated_client.post(f"/assistant/{auto.id}/confirm", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(AssistantInteraction, auto.id)
    assert refreshed is not None
    assert refreshed.confirmation_status == "auto"
    # No duplicate grocery item.
    assert len(db_session.scalars(select(GroceryItem)).all()) == 1


def test_assistant_confirm_rejects_other_users_interaction(
    authenticated_client: TestClient, fake_llm: FakeLLM, db_session: Session
) -> None:
    from family_assistant.auth.models import User
    from family_assistant.auth.services import hash_password

    other = User(name="Bob", email="bob@example.com", password_hash=hash_password("nope"))
    db_session.add(other)
    db_session.commit()
    pending = AssistantInteraction(
        user_id=other.id,
        input_text="add five things",
        proposed_tool_calls=[
            {
                "name": "grocery.add_items",
                "args": {"items": [{"name": n} for n in ["a", "b", "c", "d", "e"]]},
                "validation": "ok",
            }
        ],
        confirmation_status="pending_confirmation",
        executed_tool_calls=[],
        affected_record_ids={},
    )
    db_session.add(pending)
    db_session.commit()

    response = authenticated_client.post(f"/assistant/{pending.id}/confirm", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(AssistantInteraction, pending.id)
    assert refreshed is not None
    assert refreshed.confirmation_status == "pending_confirmation"
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_assistant_cancel_rejects_other_users_interaction(
    authenticated_client: TestClient, db_session: Session
) -> None:
    from family_assistant.auth.models import User
    from family_assistant.auth.services import hash_password

    other = User(name="Bob", email="bob@example.com", password_hash=hash_password("nope"))
    db_session.add(other)
    db_session.commit()
    pending = AssistantInteraction(
        user_id=other.id,
        input_text="something",
        proposed_tool_calls=[],
        confirmation_status="pending_confirmation",
        executed_tool_calls=[],
        affected_record_ids={},
    )
    db_session.add(pending)
    db_session.commit()

    response = authenticated_client.post(f"/assistant/{pending.id}/cancel", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    refreshed = db_session.get(AssistantInteraction, pending.id)
    assert refreshed is not None
    assert refreshed.confirmation_status == "pending_confirmation"


def test_dashboard_shows_recent_interactions(
    authenticated_client: TestClient, fake_llm: FakeLLM
) -> None:
    fake_llm.next_response = {
        "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Eggs"}]}}],
        "reply": "Added eggs.",
    }
    authenticated_client.post("/assistant", data={"input_text": "add eggs to grocery"})

    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert b"add eggs to grocery" in response.content
    assert b"No interactions yet" not in response.content
