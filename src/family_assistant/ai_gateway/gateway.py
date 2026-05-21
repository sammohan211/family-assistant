"""AI Gateway entry point (PRD Sections 11, 16.7).

`process_command` is the single internal entry consumed by the assistant
router. Orchestrates: build prompt → call LLM → validate tool calls →
classify risk → execute (low-risk auto, medium/high stage for confirmation)
→ log AssistantInteraction.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.llm import LLMClient, OllamaClient
from family_assistant.ai_gateway.models import AssistantInteraction
from family_assistant.ai_gateway.prompt import build_context, render_messages
from family_assistant.ai_gateway.risk import RiskTier, classify
from family_assistant.ai_gateway.tools import (
    ToolResult,
    ToolValidationError,
    ValidatedToolCall,
    execute_tool_call,
    validate_tool_call,
)
from family_assistant.ai_gateway.tracing import TraceRecorder
from family_assistant.auth.models import User


@dataclass
class GatewayResult:
    interaction_id: int
    reply: str
    confirmation_status: str
    risk: RiskTier
    proposed_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    executed_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _serialize_proposed(
    calls: list[ValidatedToolCall], errors: list[ToolValidationError]
) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for call in calls:
        serialized.append({"name": call.name, "args": call.raw_args, "validation": "ok"})
    for err in errors:
        serialized.append(
            {"name": err.name, "args": err.raw_args, "validation": "error", "error": err.error}
        )
    return serialized


def _serialize_executed(
    calls: list[ValidatedToolCall], results: list[ToolResult]
) -> list[dict[str, Any]]:
    return [
        {
            "name": call.name,
            "args": call.raw_args,
            "outcome": result.outcome,
            "affected_table": result.affected_table,
            "affected_ids": result.affected_ids,
            "error": result.error,
        }
        for call, result in zip(calls, results, strict=True)
    ]


def _affected_record_ids(
    calls: list[ValidatedToolCall], results: list[ToolResult]
) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for _call, result in zip(calls, results, strict=True):
        if result.outcome != "success" or not result.affected_table:
            continue
        grouped.setdefault(result.affected_table, []).extend(result.affected_ids)
    return grouped


def process_command(
    user: User,
    input_text: str,
    db: DbSession,
    llm: LLMClient | None = None,
) -> GatewayResult:
    started = time.monotonic()
    llm = llm or OllamaClient()
    tracer = TraceRecorder(_start=started)

    tracer.log("input", "received", {"user_id": user.id, "input_chars": len(input_text)})

    context = build_context(db, input_text)
    messages = render_messages(context, input_text)
    tracer.log(
        "context",
        "built",
        {
            "message_count": len(messages),
            "prompt_chars": sum(len(m.get("content", "")) for m in messages),
        },
    )

    error_log: str | None = None
    reply: str = ""
    raw_calls: list[dict[str, Any]] = []

    tracer.log("llm", "call_started", {})
    try:
        response = llm.chat_json(messages)
        reply = str(response.get("reply", "") or "")
        raw_calls = list(response.get("tool_calls") or [])
        tracer.log(
            "llm",
            "call_succeeded",
            {"reply_chars": len(reply), "tool_call_count": len(raw_calls)},
        )
    except Exception as exc:
        error_log = f"LLM call failed: {type(exc).__name__}: {exc}"
        tracer.log("llm", "call_failed", {"error": error_log})

    validated: list[ValidatedToolCall] = []
    validation_errors: list[ToolValidationError] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            validation_errors.append(
                ToolValidationError(
                    name="<malformed>", raw_args={}, error=f"Not an object: {raw!r}"
                )
            )
            continue
        name = str(raw.get("name", ""))
        args = raw.get("args") or {}
        if not isinstance(args, dict):
            validation_errors.append(
                ToolValidationError(
                    name=name, raw_args={}, error=f"args is not an object: {args!r}"
                )
            )
            continue
        outcome = validate_tool_call(name, args)
        if isinstance(outcome, ToolValidationError):
            validation_errors.append(outcome)
        else:
            validated.append(outcome)

    tracer.log(
        "validation",
        "completed",
        {
            "validated_count": len(validated),
            "error_count": len(validation_errors),
            "validated_names": [c.name for c in validated],
            "error_names": [e.name for e in validation_errors],
        },
    )

    risk: RiskTier = classify(validated)
    tracer.log("risk", "classified", {"tier": risk})
    proposed = _serialize_proposed(validated, validation_errors)

    executed_serialized: list[dict[str, Any]] = []
    affected: dict[str, list[int]] = {}
    confirmation_status: str

    if error_log is not None:
        confirmation_status = "auto"
        if not reply:
            reply = "Sorry, I couldn't reach the assistant right now. Please try again."
        tracer.log("decision", "auto", {"branch": "llm_error"})
    elif not validated and not validation_errors:
        confirmation_status = "auto"
        tracer.log("decision", "auto", {"branch": "no_tool_calls"})
    elif validation_errors and not validated:
        # Every proposed call failed validation — nothing safe to confirm or execute.
        # Always overwrite reply: the LLM often claims success ("items added") even
        # when its tool call was malformed, and we never want to show that to the user.
        confirmation_status = "auto"
        error_log = "Tool validation failed: " + "; ".join(e.error for e in validation_errors)
        reply = (
            "I couldn't act on that — the assistant produced an invalid action. Please rephrase."
        )
        tracer.log("decision", "validation_error", {"branch": "all_invalid"})
    elif risk == "low" and validated and not validation_errors:
        results = [execute_tool_call(call, db, user) for call in validated]
        executed_serialized = _serialize_executed(validated, results)
        affected = _affected_record_ids(validated, results)
        confirmation_status = "auto"
        if any(r.outcome != "success" for r in results):
            error_log = "; ".join(r.error for r in results if r.error) or None
        tracer.log(
            "execution",
            "completed",
            {
                "outcomes": [r.outcome for r in results],
                "affected": affected,
            },
        )
        tracer.log("decision", "auto", {"branch": "low_risk_executed"})
    else:
        confirmation_status = "pending_confirmation"
        if not reply:
            reply = "I need your confirmation before doing this. See the proposed actions above."
        tracer.log("decision", "pending_confirmation", {"risk": risk})

    latency_ms = int((time.monotonic() - started) * 1000)

    interaction = AssistantInteraction(
        user_id=user.id,
        input_text=input_text,
        reply=reply,
        parsed_intent=None,
        parsed_entities=None,
        proposed_tool_calls=proposed,
        confirmation_status=confirmation_status,
        executed_tool_calls=executed_serialized,
        affected_record_ids=affected,
        latency_ms=latency_ms,
        error_log=error_log,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)

    tracer.log(
        "persist",
        "interaction_saved",
        {
            "interaction_id": interaction.id,
            "confirmation_status": confirmation_status,
            "latency_ms": latency_ms,
        },
    )
    tracer.flush(db, interaction.id)

    return GatewayResult(
        interaction_id=interaction.id,
        reply=reply,
        confirmation_status=confirmation_status,
        risk=risk,
        proposed_tool_calls=proposed,
        executed_tool_calls=executed_serialized,
        validation_errors=[
            {"name": e.name, "args": e.raw_args, "error": e.error} for e in validation_errors
        ],
        error=error_log,
    )


def confirm_pending(
    interaction: AssistantInteraction, db: DbSession, user: User
) -> AssistantInteraction:
    """Execute the previously-validated tool calls on a pending interaction."""
    tracer = TraceRecorder()
    if interaction.confirmation_status != "pending_confirmation":
        return interaction
    validated: list[ValidatedToolCall] = []
    for proposed in interaction.proposed_tool_calls:
        if proposed.get("validation") != "ok":
            continue
        outcome = validate_tool_call(str(proposed.get("name", "")), proposed.get("args") or {})
        if isinstance(outcome, ValidatedToolCall):
            validated.append(outcome)
    if not validated:
        # Nothing valid to execute — don't pretend we approved anything.
        tracer.log("confirm", "nothing_to_execute", {"interaction_id": interaction.id})
        tracer.flush(db, interaction.id)
        return interaction
    results = [execute_tool_call(call, db, user) for call in validated]
    interaction.executed_tool_calls = _serialize_executed(validated, results)
    interaction.affected_record_ids = _affected_record_ids(validated, results)
    interaction.confirmation_status = "approved"
    errors = [r.error for r in results if r.error]
    if errors:
        interaction.error_log = "; ".join(errors)
    db.commit()
    db.refresh(interaction)
    tracer.log(
        "confirm",
        "approved",
        {
            "interaction_id": interaction.id,
            "outcomes": [r.outcome for r in results],
            "affected": interaction.affected_record_ids,
        },
    )
    tracer.flush(db, interaction.id)
    return interaction


def cancel_pending(interaction: AssistantInteraction, db: DbSession) -> AssistantInteraction:
    """Mark a pending interaction as cancelled without executing anything."""
    tracer = TraceRecorder()
    if interaction.confirmation_status != "pending_confirmation":
        return interaction
    interaction.confirmation_status = "cancelled"
    db.commit()
    db.refresh(interaction)
    tracer.log("cancel", "cancelled", {"interaction_id": interaction.id})
    tracer.flush(db, interaction.id)
    return interaction
