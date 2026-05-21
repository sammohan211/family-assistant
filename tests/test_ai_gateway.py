"""AI Gateway tests with a fake LLM client."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.ai_gateway import cancel_pending, confirm_pending, process_command
from family_assistant.ai_gateway.llm_mock import MockLLMClient
from family_assistant.ai_gateway.models import AssistantInteraction, InteractionTrace
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


# Required identifier fields (name/title/content/exercise_name) must reject
# whitespace-only LLM output so blank rows can't be persisted via the assistant.
def test_validate_tool_call_rejects_blank_grocery_name() -> None:
    err = validate_tool_call("grocery.add_items", {"items": [{"name": "   "}]})
    assert err.error is not None  # type: ignore[union-attr]
    assert "name" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_rejects_blank_meal_title() -> None:
    err = validate_tool_call(
        "meal_plan.create_entry",
        {"date": date.today().isoformat(), "meal_type": "dinner", "title": "  "},
    )
    assert err.error is not None  # type: ignore[union-attr]
    assert "title" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_rejects_blank_lunch_item_name() -> None:
    err = validate_tool_call(
        "lunch_plan.create_entry",
        {
            "family_member_id": 1,
            "date": date.today().isoformat(),
            "items": [{"name": "\t\n"}],
        },
    )
    assert err.error is not None  # type: ignore[union-attr]
    assert "name" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_rejects_blank_memory_content() -> None:
    err = validate_tool_call(
        "memory.create",
        {
            "subject_type": "household",
            "memory_type": "preference",
            "content": " ",
        },
    )
    assert err.error is not None  # type: ignore[union-attr]
    assert "content" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_rejects_blank_exercise_name() -> None:
    err = validate_tool_call(
        "exercise.log_activity",
        {"exercise_name": "  ", "date": date.today().isoformat()},
    )
    assert err.error is not None  # type: ignore[union-attr]
    assert "exercise_name" in err.error.lower()  # type: ignore[union-attr]


def test_validate_tool_call_strips_whitespace_on_required_strings() -> None:
    ok = validate_tool_call("grocery.add_items", {"items": [{"name": "  milk  "}]})
    assert isinstance(ok, ValidatedToolCall)
    assert ok.args.items[0].name == "milk"  # type: ignore[attr-defined]


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


def test_process_command_blank_required_string_does_not_stage(
    db_session: Session, seeded_user: User
) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "   "}]}}],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "add nothing", db_session, llm=llm)

    assert result.confirmation_status == "auto"
    assert db_session.scalars(select(GroceryItem)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.proposed_tool_calls[0]["validation"] == "error"
    assert interaction.error_log is not None and "name" in interaction.error_log.lower()


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


# --- Tracing ---------------------------------------------------------------


def _traces_for(db: Session, interaction_id: int) -> list[InteractionTrace]:
    return list(
        db.scalars(
            select(InteractionTrace)
            .where(InteractionTrace.interaction_id == interaction_id)
            .order_by(InteractionTrace.id)
        ).all()
    )


def _events(traces: list[InteractionTrace]) -> list[tuple[str, str]]:
    return [(t.stage, t.event) for t in traces]


def test_tracing_records_full_low_risk_sequence(db_session: Session, seeded_user: User) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "Milk"}]}}],
            "reply": "Added milk.",
        }
    )

    result = process_command(seeded_user, "add milk", db_session, llm=llm)

    events = _events(_traces_for(db_session, result.interaction_id))
    assert events == [
        ("input", "received"),
        ("context", "built"),
        ("llm", "call_started"),
        ("llm", "call_succeeded"),
        ("validation", "completed"),
        ("risk", "classified"),
        ("execution", "completed"),
        ("decision", "auto"),
        ("persist", "interaction_saved"),
    ]


def test_tracing_records_llm_failure(db_session: Session, seeded_user: User) -> None:
    result = process_command(seeded_user, "anything", db_session, llm=BrokenLLM())

    traces = _traces_for(db_session, result.interaction_id)
    events = _events(traces)
    assert ("llm", "call_failed") in events
    assert ("llm", "call_succeeded") not in events
    failed = next(t for t in traces if t.event == "call_failed")
    assert "ollama is on fire" in failed.payload["error"]


def test_tracing_records_validation_error_branch(db_session: Session, seeded_user: User) -> None:
    llm = FakeLLM(
        {
            "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "   "}]}}],
            "reply": "",
        }
    )
    result = process_command(seeded_user, "add nothing", db_session, llm=llm)

    traces = _traces_for(db_session, result.interaction_id)
    events = _events(traces)
    assert ("decision", "validation_error") in events
    validation = next(t for t in traces if t.event == "completed" and t.stage == "validation")
    assert validation.payload["validated_count"] == 0
    assert validation.payload["error_count"] == 1


def test_tracing_records_pending_confirmation_and_confirm(
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

    pre_confirm = _events(_traces_for(db_session, result.interaction_id))
    assert ("decision", "pending_confirmation") in pre_confirm

    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    confirm_pending(interaction, db_session, seeded_user)

    post_confirm = _events(_traces_for(db_session, result.interaction_id))
    # Pre-confirm events are still there, plus the new confirm row.
    assert post_confirm[: len(pre_confirm)] == pre_confirm
    assert ("confirm", "approved") in post_confirm


def test_tracing_records_cancel(db_session: Session, seeded_user: User) -> None:
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
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    cancel_pending(interaction, db_session)

    events = _events(_traces_for(db_session, result.interaction_id))
    assert ("cancel", "cancelled") in events


def test_tracing_ts_ms_is_monotonic(db_session: Session, seeded_user: User) -> None:
    llm = FakeLLM({"tool_calls": [], "reply": "ok"})
    result = process_command(seeded_user, "anything", db_session, llm=llm)

    traces = _traces_for(db_session, result.interaction_id)
    ts = [t.ts_ms for t in traces]
    # Trace timestamps are monotonic-offset milliseconds from request start so
    # the sequence must be non-decreasing within a single call.
    assert ts == sorted(ts)
    assert ts[0] == 0 or ts[0] >= 0


# --- MockLLMClient + full pipeline -----------------------------------------
#
# These run the offline mock through process_command so the threat ↔ defense
# pairing is asserted end-to-end (mock emits intentional bad output, pipeline
# layers catch it). The unit tests for the mock itself live in test_llm_mock.py.


def test_mock_blank_name_routes_to_validation_error(db_session: Session, seeded_user: User) -> None:
    mock = MockLLMClient(force_mode="blank_name")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.confirmation_status == "auto"
    assert result.error is not None and "validation" in result.error.lower()
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_mock_unknown_tool_routes_to_validation_error(
    db_session: Session, seeded_user: User
) -> None:
    mock = MockLLMClient(force_mode="unknown_tool")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.confirmation_status == "auto"
    assert result.error is not None and "unknown tool" in result.error.lower()


def test_mock_bad_args_shape_routes_to_validation_error(
    db_session: Session, seeded_user: User
) -> None:
    mock = MockLLMClient(force_mode="bad_args_shape")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.confirmation_status == "auto"
    assert result.error is not None
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_mock_hallucinated_fk_records_not_found(db_session: Session, seeded_user: User) -> None:
    mock = MockLLMClient(force_mode="hallucinated_fk")
    result = process_command(seeded_user, "pack lunch for ghost", db_session, llm=mock)

    assert db_session.scalars(select(LunchPlanEntry)).all() == []
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    # Lunch plan validation runs in services (FK check), not the schema layer,
    # so this surfaces as an executed call with outcome=not_found.
    assert interaction.executed_tool_calls[0]["outcome"] == "not_found"


def test_mock_hard_restriction_routes_to_pending_confirmation(
    db_session: Session, seeded_user: User
) -> None:
    mock = MockLLMClient(force_mode="hard_restriction")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.risk == "high"
    assert result.confirmation_status == "pending_confirmation"
    assert db_session.scalars(select(Memory)).all() == []


def test_mock_bulk_grocery_routes_to_pending_confirmation(
    db_session: Session, seeded_user: User
) -> None:
    mock = MockLLMClient(force_mode="bulk_grocery")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.risk == "medium"
    assert result.confirmation_status == "pending_confirmation"
    # Nothing executes until confirm.
    assert db_session.scalars(select(GroceryItem)).all() == []


def test_mock_crash_routes_to_llm_error(db_session: Session, seeded_user: User) -> None:
    mock = MockLLMClient(force_mode="crash")
    result = process_command(seeded_user, "anything", db_session, llm=mock)

    assert result.error is not None and "mock LLM forced crash" in result.error
    interaction = db_session.get(AssistantInteraction, result.interaction_id)
    assert interaction is not None
    assert interaction.error_log is not None
    # The trace should show the failure stage.
    events = _events(_traces_for(db_session, result.interaction_id))
    assert ("llm", "call_failed") in events


def test_mock_keyword_routing_runs_end_to_end(db_session: Session, seeded_user: User) -> None:
    # Without force_mode the mock matches on the user message — exercise the
    # happy path so offline UI dev produces real DB writes.
    mock = MockLLMClient()
    result = process_command(seeded_user, "add milk to the grocery list", db_session, llm=mock)

    assert result.confirmation_status == "auto"
    assert mock.last_label == "grocery"
    items = db_session.scalars(select(GroceryItem)).all()
    assert [i.name for i in items] == ["Milk"]
