"""LLM client interface + Ollama implementation.

A thin Protocol so tests can inject a fake. Real client wraps Ollama's
`/api/chat` endpoint with `format: "json"` for structured output.
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
