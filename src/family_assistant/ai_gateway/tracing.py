"""Per-stage observability for AI Gateway runs.

`TraceRecorder` buffers `(stage, event, payload)` tuples during a
`process_command` (or confirm/cancel) call and flushes them to
`interaction_traces` once the parent `assistant_interactions` row has an id.

The (stage, event) pair names *which layer* made *which* decision:

    stage         events
    -----         ------
    input         received
    context       built
    llm           call_started, call_succeeded, call_failed
    validation    completed
    risk          classified
    decision      auto, validation_error, pending_confirmation
    execution     completed
    persist       interaction_saved
    confirm       approved, nothing_to_execute
    cancel        cancelled

Payloads are free-form JSONB so adding fields doesn't require a migration.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.models import InteractionTrace


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce payload to JSON-serializable form before write.

    JSONB requires serializable data and most call sites pass plain dicts, but
    a stray dataclass or datetime would crash the whole interaction. Round-trip
    through json with default=str so the trace remains best-effort, not a
    failure mode for the request.
    """
    try:
        return json.loads(json.dumps(payload, default=str))
    except (TypeError, ValueError) as exc:
        return {"_unserializable": repr(payload), "_error": str(exc)}


@dataclass
class TraceRecorder:
    """In-memory event buffer for one orchestration call.

    Buffer-then-flush is required because trace events fire before the parent
    `AssistantInteraction` row has an id. After the parent row is committed,
    call `flush(db, interaction_id)` to materialize the trace rows.
    """

    _start: float = field(default_factory=time.monotonic)
    _events: list[tuple[int, str, str, dict[str, Any]]] = field(default_factory=list)

    def log(self, stage: str, event: str, payload: dict[str, Any] | None = None) -> None:
        ts_ms = int((time.monotonic() - self._start) * 1000)
        self._events.append((ts_ms, stage, event, _safe_payload(payload or {})))

    def flush(self, db: DbSession, interaction_id: int) -> None:
        if not self._events:
            return
        rows = [
            InteractionTrace(
                interaction_id=interaction_id,
                ts_ms=ts_ms,
                stage=stage,
                event=event,
                payload=payload,
            )
            for ts_ms, stage, event, payload in self._events
        ]
        db.add_all(rows)
        db.commit()
        self._events.clear()

    @property
    def events(self) -> list[tuple[int, str, str, dict[str, Any]]]:
        """Read-only view, useful for tests."""
        return list(self._events)
