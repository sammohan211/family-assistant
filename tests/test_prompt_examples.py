"""Prompt-contract tests for the AI Gateway system prompt.

Two guards live here:

1. Every ``Output:`` JSON snippet in ``SYSTEM_PROMPT`` must parse and every
   tool_call inside it must pass ``validate_tool_call`` against the live
   Pydantic schemas. If an example drifts from the backend contract (e.g. an
   arg is renamed, a required field is dropped, ``NonEmptyStr`` is applied to a
   new field) the build fails here instead of silently mis-teaching the LLM.

2. The relevance heuristics that gate context fetching must not fire on
   cross-domain phrases. Regression guard for the false positives discussed in
   the prompt-review pass ("add a family member" must not pull the grocery
   list, etc.).
"""

from __future__ import annotations

import json
import re

import pytest

from family_assistant.ai_gateway.prompt import (
    SYSTEM_PROMPT,
    _grocery_relevant,
    _lunch_relevant,
    _meal_relevant,
)
from family_assistant.ai_gateway.tools import ToolValidationError, validate_tool_call

_OUTPUT_LINE = re.compile(r"^Output: (\{.*\})\s*$", re.MULTILINE)


def _extract_examples() -> list[dict]:
    """Parse every `Output: {...}` line in SYSTEM_PROMPT into a dict."""
    matches = _OUTPUT_LINE.findall(SYSTEM_PROMPT)
    assert matches, "No Output: examples found in SYSTEM_PROMPT — regex drift?"
    return [json.loads(m) for m in matches]


def test_system_prompt_has_examples() -> None:
    # Sanity: the parser found something. Updated if/when examples are trimmed.
    examples = _extract_examples()
    assert len(examples) >= 10, f"Expected >=10 examples, found {len(examples)}"


@pytest.mark.parametrize("example", _extract_examples())
def test_prompt_example_tool_calls_validate(example: dict) -> None:
    """Every tool_call in every example must validate against its schema.

    Empty tool_calls lists (ask-instead-of-act examples) are skipped — there is
    no contract to check.
    """
    assert "tool_calls" in example, f"Example missing tool_calls key: {example}"
    assert "reply" in example, f"Example missing reply key: {example}"

    for call in example["tool_calls"]:
        assert "name" in call, f"Tool call missing name: {call}"
        assert "args" in call, f"Tool call missing args: {call}"
        result = validate_tool_call(call["name"], call["args"])
        assert not isinstance(result, ToolValidationError), (
            f"Example tool_call failed schema validation: "
            f"name={call['name']!r} args={call['args']!r} error={getattr(result, 'error', None)}"
        )


# --- Relevance heuristics --------------------------------------------------
#
# Regression guard: pruning "add" / "list" / "plan" from the token sets means
# unrelated domain commands no longer pull the wrong context block.


@pytest.mark.parametrize(
    "text",
    [
        "add milk to the grocery list",
        "buy bread tomorrow",
        "I bought eggs",
        "mark cheese as purchased",
        "what's on my shopping list",
    ],
)
def test_grocery_relevant_true_for_grocery_phrases(text: str) -> None:
    assert _grocery_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "add a family member named Lila",
        "list memories about allergies",
        "remember that Lila loves cucumbers",
        "log a 5k run today",
        "schedule dinner for Saturday",  # meal, not grocery
    ],
)
def test_grocery_relevant_false_for_unrelated(text: str) -> None:
    assert not _grocery_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "what's for dinner",
        "plan a breakfast for Sunday",
        "I'll cook tonight",
        "let's eat at 7",
    ],
)
def test_meal_relevant_true_for_meal_phrases(text: str) -> None:
    assert _meal_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "add milk to the list",
        "list memories",
        "remember Lila's allergy",
        "log a run today",
        "pack lunch for Lila tomorrow",  # should fire lunch, not meal
    ],
)
def test_meal_relevant_false_for_unrelated(text: str) -> None:
    assert not _meal_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "pack lunch for Lila tomorrow",
        "school lunch ideas",
        "what did I pack yesterday",
    ],
)
def test_lunch_relevant_true_for_lunch_phrases(text: str) -> None:
    assert _lunch_relevant(text)


@pytest.mark.parametrize(
    "text",
    [
        "add milk",
        "remember Lila's allergy",
        "schedule dinner",
        "log a run",
    ],
)
def test_lunch_relevant_false_for_unrelated(text: str) -> None:
    assert not _lunch_relevant(text)
