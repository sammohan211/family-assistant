"""LLM client interface + provider implementations.

A thin Protocol so tests can inject a fake. Two real clients implement it:

- `OllamaClient` wraps Ollama's `/api/chat` with `format: "json"` (local /
  self-hosted inference; the home/GPU deployment).
- `OpenRouterClient` wraps OpenRouter's OpenAI-compatible
  `/v1/chat/completions` with `response_format: {"type": "json_object"}`
  (cloud deployment with no local GPU).

`default_client()` picks one from settings (`LLM_PROVIDER`). The offline
`MockLLMClient` is selected one layer up, in the assistant dependency, since
it's tied to the web app / tests rather than the inference transport.
"""

import json
from typing import Any, Protocol

import httpx

from family_assistant.settings import get_settings


class LLMClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        num_ctx: int | None = None,
        timeout: float = 180.0,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._num_ctx = num_ctx or settings.ollama_num_ctx
        self._timeout = timeout
        # Set by chat_json so the gateway can record it in the trace; None
        # until the first successful call. Default 4096 silently truncated
        # real prompts — surfacing this lets future drift be caught fast.
        self.last_prompt_tokens: int | None = None
        self.last_num_ctx: int | None = None

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "format": "json",
                "stream": False,
                "messages": messages,
                "options": {"num_ctx": self._num_ctx},
            },
            timeout=httpx.Timeout(connect=10.0, read=self._timeout, write=10.0, pool=10.0),
        )
        response.raise_for_status()
        body = response.json()
        self.last_prompt_tokens = body.get("prompt_eval_count")
        self.last_num_ctx = self._num_ctx
        content = body["message"]["content"]
        return json.loads(content)


class OpenRouterClient:
    """OpenAI-compatible client for OpenRouter (cloud, no local GPU).

    Same `LLMClient` surface as `OllamaClient`, including the
    `last_prompt_tokens` / `last_num_ctx` attributes the gateway reads for
    tracing. There's no local context window we control on a hosted model, so
    `last_num_ctx` stays `None` — the gateway's prompt-near-ceiling check is
    guarded on `num_ctx is not None` and simply skips for this provider.

    The selected model must support JSON output via `response_format`; the
    system prompt already instructs JSON, so models that ignore the field but
    still emit JSON also work. Invalid JSON raises `json.JSONDecodeError`,
    which `process_command` catches and turns into a graceful failure.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        settings = get_settings()
        key = api_key or settings.openrouter_api_key
        if not key:
            raise ValueError(
                "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter. "
                "Set it in .env (see .env.example)."
            )
        self._api_key = key
        self._base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self._model = model or settings.openrouter_model
        self._timeout = timeout
        # OpenRouter uses these (optional) headers for app attribution /
        # leaderboard ranking; harmless when unset.
        self._app_url = settings.openrouter_app_url
        self._app_title = settings.openrouter_app_title
        self.last_prompt_tokens: int | None = None
        self.last_num_ctx: int | None = None

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._app_url:
            headers["HTTP-Referer"] = self._app_url
        if self._app_title:
            headers["X-Title"] = self._app_title
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json={
                "model": self._model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            timeout=httpx.Timeout(connect=10.0, read=self._timeout, write=10.0, pool=10.0),
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        self.last_prompt_tokens = usage.get("prompt_tokens")
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)


def default_client() -> LLMClient:
    """Pick the live LLM client from settings (`LLM_PROVIDER`).

    Does not handle the offline mock — that's selected in the assistant
    dependency (`get_llm`), since it's tied to the web app and tests rather
    than the inference transport.
    """
    provider = get_settings().llm_provider
    if provider == "openrouter":
        return OpenRouterClient()
    if provider == "ollama":
        return OllamaClient()
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}. Expected 'ollama' or 'openrouter'.")
