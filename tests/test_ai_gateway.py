"""AI Gateway tests with a fake LLM client."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.ai_gateway import process_command
from family_assistant.ai_gateway.models import AssistantInteraction
from family_assistant.ai_gateway.risk import classify
from family_assistant.ai_gateway.tools import (
    GroceryAddItemsArgs,
    ValidatedToolCall,
    validate_tool_call,
)
from family_assistant.auth.models import User
from family_assistant.family_member.models import FamilyMember
from family_assistant.grocery.models import GroceryItem
from family_assistant.lunch_plan.models import LunchPlanEntry
from family_assistant.meal_plan.models import MealPlanEntry
from family_assistant.memory.models import Memory


class FakeLLM:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.calls.append(messages)
        return self.response


class BrokenLLM:
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        raise RuntimeError("ollama is on fire")


# --- Tool validation -------------------------------------------------------


def test_validate_tool_call_unknown_tool() -> None:
    err = validate_tool_call("not_a_tool", {})
    assert err.error.startswith("Unknown tool")  # type: ignore[union-attr]


def test_validate_tool_call_missing_required_field() -> None:
    err = validate_tool_call("grocery.add_items", {})
    assert "items" in err.error  # type: ignore[union-attr]


def test_validate_tool_call_rejects_extra_fields() -> None:
    err = validate_tool_call("grocery.add_items", {"items": [{"name": "milk"}], "extra": "nope"})
    assert "extra" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_ok() -> None:
    ok = validate_tool_call("grocery.add_items", {"items": [{"name": "milk"}]})
    assert isinstance(ok, ValidatedToolCall)
    assert isinstance(ok.args, GroceryAddItemsArgs)


# --- Risk classifier -------------------------------------------------------


def _wrap(name: str, args: dict[str, Any]) -> ValidatedToolCall:
    result = validate_tool_call(name, args)
    assert isinstance(result, ValidatedToolCall), result
    return result


def test_risk_low_for_single_grocery_add() -> None:
    call = _wrap("grocery.add_items", {"items": [{"name": "milk"}]})
    assert classify([call]) == "low"


def test_risk_medium_for_bulk_grocery_add() -> None:
    call = _wrap(
        "grocery.add_items",
        {"items": [{"name": n} for n in ["milk", "bread", "apples", "eggs"]]},
    )
    assert classify([call]) == "medium"


def test_risk_medium_for_many_tool_calls() -> None:
    calls = [
        _wrap(
            "meal_plan.create_entry",
            {
                "date": (date.today() + timedelta(days=i)).isoformat(),
                "meal_type": "dinner",
                "title": "Pasta",
            },
        )
        for i in range(4)
    ]
    assert classify(calls) == "medium"


def test_risk_high_for_hard_restriction_memory() -> None:
    call = _wrap(
        "memory.create",
        {
            "subject_type": "family_member",
            "subject_id": 1,
            "memory_type": "restriction",
            "content": "peanut allergy",
            "is_hard_restriction": True,
        },
    )
    assert classify([call]) == "high"


def test_risk_low_for_empty() -> None:
    assert classify([]) == "low"


# --- process_command end-to-end -------------------------------------------


def test_process_command_low_risk_executes_and_logs(db_session: Session, seeded_user: User) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Milk"}]}}],
            "reply": "Added milk.",
        }
    )

    result = process_command(seeded_user, "add milk", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    assert result.risk == "low"
    assert result.reply == "Added milk."
    items = db_session.scalars(select(GroceryItem)).all()
    assert [i.name for i in items] == ["Milk"]

    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.input_text == "add milk"
    assert interaction.confirmation_status == "auto"
    assert interaction.affected_record_ids == {"grocery_items": [items[0].id]}
    assert interaction.latency_ms is not None and interaction.latency_ms >= 0


def test_process_command_medium_risk_stages_without_executing(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "grocery.add_items",
                    "args": {"items": [{"name": n} for n in ["a", "b", "c", "d", "e"]]},
                }
            ],
            "reply": "",
        }
    )

    result = process_command(seeded_user, "add a bunch", db_session, llm=llm)

    assert result.confirmation_status == "pending_confirmation"
    assert result.risk == "medium"
    assert db_session.scalars(select(GroceryItem)).all() == []
    assert result.reply  # placeholder confirmation reply

    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.confirmation_status == "pending_confirmation"
    assert interaction.executed_tool_calls == []
    assert len(interaction.proposed_tool_calls) == 1
    assert interaction.proposed_tool_calls[0]["validation"] == "ok"


def test_process_command_validation_errors_only_does_not_stage(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [{"name": "grocery.add_items", "args": {"itemz": []}}],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "broken", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    assert result.error is not None and "validation" in result.error.lower()
    assert "rephrase" in result.reply.lower()
    assert db_session.scalars(select(GroceryItem)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.confirmation_status == "auto"
    assert interaction.proposed_tool_calls[0]["validation"] == "error"
    assert interaction.error_log is not None


def test_process_command_memory_create_rejects_unknown_family_member(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "memory.create",
                    "args": {
                        "subject_type": "family_member",
                        "subject_id": 9999,
                        "memory_type": "preference",
                        "content": "anything",
                    },
                }
            ],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "remember this for nobody", db_session, llm=llm)

    assert db_session.scalars(select(Memory)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.executed_tool_calls[0]["outcome"] == "validation_error"
    assert "9999" in interaction.executed_tool_calls[0]["error"]


def test_process_command_memory_create_rejects_user_subject_without_id(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "memory.create",
                    "args": {
                        "subject_type": "user",
                        "memory_type": "preference",
                        "content": "anything",
                    },
                }
            ],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "remember this for nobody", db_session, llm=llm)

    assert db_session.scalars(select(Memory)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.executed_tool_calls[0]["outcome"] == "validation_error"


def test_process_command_no_tool_calls_is_a_read(db_session: Session, seeded_user: User) -> None:
    db_session.add(GroceryItem(name="apples", added_by_user_id=seeded_user.id))
    db_session.commit()

    llm = FakeLLM({"tool_calls": [], "reply": "Yes — apples are on the list."})
    result = process_command(seeded_user, "do I have apples?", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    assert result.reply == "Yes — apples are on the list."
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.proposed_tool_calls == []
    assert interaction.executed_tool_calls == []


def test_process_command_llm_failure_logs_and_recovers(
    db_session: Session, seeded_user: User
) -> None:
    result = process_command(seeded_user, "anything", db_session, llm=BrokenLLM())

    assert result.error is not None and "ollama is on fire" in result.error
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.error_log is not None
    assert "ollama is on fire" in interaction.error_log
    assert interaction.executed_tool_calls == []


def test_process_command_dispatches_meal_plan(db_session: Session, seeded_user: User) -> None:
    target = date.today() + timedelta(days=1)
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "meal_plan.create_entry",
                    "args": {
                        "date": target.isoformat(),
                        "meal_type": "dinner",
                        "title": "Pasta night",
                    },
                }
            ],
            "reply": "Planned pasta for tomorrow.",
        }
    )

    result = process_command(seeded_user, "plan pasta for tomorrow", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    entries = db_session.scalars(select(MealPlanEntry)).all()
    assert len(entries) == 1
    assert entries[0].title == "Pasta night"
    assert entries[0].date == target


def test_process_command_lunch_plan_requires_existing_family_member(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "lunch_plan.create_entry",
                    "args": {
                        "family_member_id": 9999,
                        "date": date.today().isoformat(),
                        "items": [{"name": "sandwich"}],
                    },
                }
            ],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "pack lunch", db_session, llm=llm)

    assert db_session.scalars(select(LunchPlanEntry)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.executed_tool_calls[0]["outcome"] == "not_found"


def test_process_command_lunch_plan_success(db_session: Session, seeded_user: User) -> None:
    member = FamilyMember(name="Lila")
    db_session.add(member)
    db_session.commit()
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "lunch_plan.create_entry",
                    "args": {
                        "family_member_id": member.id,
                        "date": date.today().isoformat(),
                        "items": [{"name": "sandwich"}, {"name": "apple"}],
                        "packed_status": "packed",
                    },
                }
            ],
            "reply": "Packed Lila's lunch.",
        }
    )
    result = process_command(seeded_user, "pack lila lunch", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    entries = db_session.scalars(select(LunchPlanEntry)).all()
    assert len(entries) == 1
    assert entries[0].family_member_id == member.id
    assert entries[0].packed_status == "packed"


def test_process_command_memory_create_records_source_assistant(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "memory.create",
                    "args": {
                        "subject_type": "household",
                        "memory_type": "preference",
                        "content": "we like one-pot meals on weekdays",
                    },
                }
            ],
            "reply": "Saved.",
        }
    )
    result = process_command(seeded_user, "remember we like one-pot meals", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    memories = db_session.scalars(select(Memory)).all()
    assert len(memories) == 1
    assert memories[0].source == "assistant"
    assert memories[0].subject_type == "household"


def test_process_command_hard_restriction_memory_requires_confirmation(
    db_session: Session, seeded_user: User
) -> None:
    member = FamilyMember(name="Lila")
    db_session.add(member)
    db_session.commit()
    llm = FakeLLM(
        {
            "tool_calls": [
                {
                    "name": "memory.create",
                    "args": {
                        "subject_type": "family_member",
                        "subject_id": member.id,
                        "memory_type": "restriction",
                        "content": "peanut allergy",
                        "is_hard_restriction": True,
                    },
                }
            ],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "lila is allergic to peanuts", db_session, llm=llm)

    assert result.risk == "high"
    assert result.confirmation_status == "pending_confirmation"
    assert db_session.scalars(select(Memory)).all() == []


# --- Prompt context smoke test --------------------------------------------


def test_prompt_includes_open_grocery_items_for_grocery_command(
    db_session: Session, seeded_user: User
) -> None:
    db_session.add(GroceryItem(name="apples", added_by_user_id=seeded_user.id))
    db_session.commit()
    llm = FakeLLM({"tool_calls": [], "reply": "Yes."})

    process_command(seeded_user, "do I have apples on the list?", db_session, llm=llm)

    [system, _user] = llm.calls[0]
    assert "apples" in system["content"]


def test_prompt_omits_grocery_items_for_unrelated_command(
    db_session: Session, seeded_user: User
) -> None:
    db_session.add(GroceryItem(name="apples", added_by_user_id=seeded_user.id))
    db_session.commit()
    llm = FakeLLM({"tool_calls": [], "reply": "ok"})

    process_command(seeded_user, "log 30 minutes cycling", db_session, llm=llm)

    [system, _user] = llm.calls[0]
    assert "open_grocery_items" in system["content"]
    assert '"apples"' not in system["content"]
