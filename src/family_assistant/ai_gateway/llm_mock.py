"""Offline mock LLM client with intentional failure modes.

Two use cases:

1. **Offline app dev.** With `USE_MOCK_LLM=true` in `.env`, `get_llm()` returns
   this client and the assistant runs without Ollama. Lets you exercise the
   UI on machines without a GPU / inference server.

2. **End-to-end tests.** Force a specific failure mode (`mode="blank_name"`)
   and run `process_command` through the real validation, risk, and tracing
   layers to assert the *pipeline* behaves correctly — not just the schema.

The failure modes are the pedagogical point: each one is paired with a
defense elsewhere in the stack.

    mode                 defends
    ----                 -------
    blank_name           NonEmptyStr in tools.py
    unknown_tool         validate_tool_call's tool registry
    bad_args_shape       validate_tool_call's args-is-object check
    hallucinated_fk      services FK validation (lunch_plan, memory)
    hard_restriction     risk.classify → pending_confirmation
    bulk_grocery         risk.classify → pending_confirmation (size threshold)
    crash                process_command's try/except + auto fallback
    prompt_injection     reply-only fallback (assistant claims success but
                         emits no tool call)

The default behavior (no `force_mode`) is keyword-driven: match the most
recent user message against a list of `Scenario` patterns and pick the first
hit. Falls back to a no-op response.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


# Failure-mode responses are functions so they can reference today's date
# without baking a stale string into the module.

ResponseFn = Callable[[], dict[str, Any]]


def _good_grocery() -> dict[str, Any]:
    return {
        "tool_calls": [
            {"name": "grocery.add_items", "args": {"items": [{"name": "Milk"}]}},
        ],
        "reply": "Added milk to the grocery list.",
    }


def _good_meal_plan() -> dict[str, Any]:
    return {
        "tool_calls": [
            {
                "name": "meal_plan.create_entry",
                "args": {"date": _tomorrow(), "meal_type": "dinner", "title": "Pasta"},
            }
        ],
        "reply": "Planned pasta for dinner tomorrow.",
    }


def _good_memory_household() -> dict[str, Any]:
    return {
        "tool_calls": [
            {
                "name": "memory.create",
                "args": {
                    "subject_type": "household",
                    "memory_type": "preference",
                    "content": "we like one-pot meals on weeknights",
                },
            }
        ],
        "reply": "Noted.",
    }


def _read_only() -> dict[str, Any]:
    return {"tool_calls": [], "reply": "(mock) I would answer this from the household context."}


# --- Intentional failure modes --------------------------------------------


def _blank_name() -> dict[str, Any]:
    """Whitespace-only required field — should be rejected by NonEmptyStr."""
    return {
        "tool_calls": [{"name": "grocery.add_items", "args": {"items": [{"name": "   "}]}}],
        "reply": "Added it.",
    }


def _unknown_tool() -> dict[str, Any]:
    """Tool name the registry doesn't know."""
    return {
        "tool_calls": [{"name": "grocery.invent_pizza", "args": {"flavor": "anchovy"}}],
        "reply": "Done.",
    }


def _bad_args_shape() -> dict[str, Any]:
    """args is a list instead of an object — caught before schema validation."""
    return {
        "tool_calls": [{"name": "grocery.add_items", "args": ["milk", "bread"]}],
        "reply": "Added.",
    }


def _hallucinated_fk() -> dict[str, Any]:
    """Non-existent family_member_id — services FK check rejects."""
    return {
        "tool_calls": [
            {
                "name": "lunch_plan.create_entry",
                "args": {
                    "family_member_id": 9999,
                    "date": _today(),
                    "items": [{"name": "sandwich"}],
                },
            }
        ],
        "reply": "Packed lunch.",
    }


def _hard_restriction() -> dict[str, Any]:
    """High-risk action — risk classifier forces pending_confirmation."""
    return {
        "tool_calls": [
            {
                "name": "memory.create",
                "args": {
                    "subject_type": "household",
                    "memory_type": "restriction",
                    "content": "no peanuts in the house",
                    "is_hard_restriction": True,
                },
            }
        ],
        "reply": "",
    }


def _bulk_grocery() -> dict[str, Any]:
    """Medium-risk — bulk add triggers pending_confirmation."""
    return {
        "tool_calls": [
            {
                "name": "grocery.add_items",
                "args": {
                    "items": [
                        {"name": n} for n in ["milk", "bread", "eggs", "apples", "yogurt", "cheese"]
                    ]
                },
            }
        ],
        "reply": "",
    }


def _prompt_injection_echo() -> dict[str, Any]:
    """Reply claims success without emitting a tool call.

    Mirrors a common real-world failure: the LLM is convinced it acted, but
    actually emitted no structured action. The pipeline should not surface
    the false-success reply — though today it does, which is the lesson.
    """
    return {"tool_calls": [], "reply": "Done — I've added everything you asked for."}


class MockCrashError(RuntimeError):
    """Raised by the `crash` mode to simulate an Ollama/network failure."""


# --- Scenarios -------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A keyword pattern → canned response mapping.

    `pattern` is matched against the lowercased *last user message* with
    word-boundary regex so "add" doesn't fire for "addendum".
    """

    pattern: str
    response: ResponseFn
    label: str  # human-readable, surfaces in traces/debug


DEFAULT_SCENARIOS: list[Scenario] = [
    # Failure-mode keywords (test/dev use)
    Scenario(r"\b(crash|explode|kaboom)\b", _read_only, "crash"),  # handled specially below
    Scenario(r"\b(blank|empty|whitespace)\b", _blank_name, "blank_name"),
    Scenario(r"\b(unknown.tool|invent|weird.tool)\b", _unknown_tool, "unknown_tool"),
    Scenario(r"\b(bad.args|malformed.args)\b", _bad_args_shape, "bad_args_shape"),
    Scenario(r"\b(ghost|nobody|9999)\b", _hallucinated_fk, "hallucinated_fk"),
    Scenario(r"\b(allergy|peanut|hard.restriction)\b", _hard_restriction, "hard_restriction"),
    Scenario(r"\b(bulk|big.shop|weekly.shop)\b", _bulk_grocery, "bulk_grocery"),
    Scenario(r"\bignore.previous.instructions\b", _prompt_injection_echo, "prompt_injection_echo"),
    # Happy paths (offline-dev use)
    Scenario(r"\b(grocery|shopping|buy|bought|milk|eggs|bread)\b", _good_grocery, "grocery"),
    Scenario(r"\b(dinner|breakfast|meal|cook)\b", _good_meal_plan, "meal_plan"),
    Scenario(r"\b(remember|note that)\b", _good_memory_household, "memory_household"),
]


# Test-only force-mode → response function lookup. Keep module-level so
# callers can introspect available modes via `FORCED_MODES.keys()`.
FORCED_MODES: dict[str, ResponseFn] = {
    "blank_name": _blank_name,
    "unknown_tool": _unknown_tool,
    "bad_args_shape": _bad_args_shape,
    "hallucinated_fk": _hallucinated_fk,
    "hard_restriction": _hard_restriction,
    "bulk_grocery": _bulk_grocery,
    "prompt_injection_echo": _prompt_injection_echo,
    "good_grocery": _good_grocery,
    "good_meal_plan": _good_meal_plan,
    "good_memory_household": _good_memory_household,
    "read_only": _read_only,
}


# --- Client ----------------------------------------------------------------


@dataclass
class MockLLMClient:
    """Drop-in replacement for `OllamaClient` that returns canned outputs.

    Implements the `LLMClient` protocol: `chat_json(messages) -> dict`.

    Parameters
    ----------
    scenarios:
        List of Scenario objects to match against the last user message.
        Defaults to `DEFAULT_SCENARIOS`.
    force_mode:
        If set, ignores scenario matching and returns the named failure mode
        every call. Use in tests. Special value `"crash"` raises instead of
        returning. Special value `"read_only"` returns the empty-tool-calls
        response.
    """

    scenarios: list[Scenario] = field(default_factory=lambda: list(DEFAULT_SCENARIOS))
    force_mode: str | None = None
    last_label: str | None = field(default=None, init=False)
    calls: list[list[dict[str, str]]] = field(default_factory=list, init=False)

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.calls.append(messages)

        if self.force_mode == "crash":
            self.last_label = "crash"
            raise MockCrashError("mock LLM forced crash")
        if self.force_mode:
            fn = FORCED_MODES.get(self.force_mode)
            if fn is None:
                raise ValueError(
                    f"Unknown force_mode: {self.force_mode!r}. Choose from: {sorted(FORCED_MODES)}"
                )
            self.last_label = self.force_mode
            return fn()

        user_text = _last_user_message(messages).lower()
        for scenario in self.scenarios:
            if re.search(scenario.pattern, user_text):
                if scenario.label == "crash":
                    self.last_label = "crash"
                    raise MockCrashError("mock LLM keyword-triggered crash")
                self.last_label = scenario.label
                return scenario.response()

        self.last_label = "fallback"
        return _read_only()


def _last_user_message(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""
