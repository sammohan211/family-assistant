"""Unit tests for live LLM provider clients and the provider factory.

These run without a database or a network: `httpx.post` is monkeypatched and
settings are faked. They assert request shape and response parsing, not real
inference.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from family_assistant.ai_gateway import llm as llm_module
from family_assistant.ai_gateway.llm import (
    OpenRouterClient,
    default_client,
)


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


def _openrouter_settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "llm_provider": "openrouter",
        "openrouter_api_key": "test-key",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_model": "meta-llama/llama-3.1-8b-instruct",
        "openrouter_app_url": None,
        "openrouter_app_title": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# --- OpenRouterClient ------------------------------------------------------


def test_openrouter_request_shape_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "get_settings", _openrouter_settings)
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "choices": [{"message": {"content": '{"reply": "hi", "tool_calls": []}'}}],
                "usage": {"prompt_tokens": 123},
            }
        )

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    client = OpenRouterClient()
    result = client.chat_json([{"role": "user", "content": "hello"}])

    assert result == {"reply": "hi", "tool_calls": []}
    assert client.last_prompt_tokens == 123
    # Hosted model has no local context window we control.
    assert client.last_num_ctx is None

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "meta-llama/llama-3.1-8b-instruct"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_openrouter_optional_attribution_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: _openrouter_settings(
            openrouter_app_url="https://family.example",
            openrouter_app_title="Family Assistant",
        ),
    )
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["headers"] = kwargs["headers"]
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}], "usage": {}})

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)

    OpenRouterClient().chat_json([{"role": "user", "content": "hi"}])

    assert captured["headers"]["HTTP-Referer"] == "https://family.example"
    assert captured["headers"]["X-Title"] == "Family Assistant"


def test_openrouter_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_module, "get_settings", lambda: _openrouter_settings(openrouter_api_key=None)
    )
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient()


# --- default_client factory ------------------------------------------------


def test_default_client_selects_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "get_settings", _openrouter_settings)
    assert isinstance(default_client(), OpenRouterClient)


def test_default_client_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "get_settings", lambda: SimpleNamespace(llm_provider="bogus"))
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        default_client()
