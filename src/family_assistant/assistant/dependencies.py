"""Dependencies for the assistant router (LLM client injection)."""

from family_assistant.ai_gateway.llm import LLMClient, OllamaClient
from family_assistant.ai_gateway.llm_mock import MockLLMClient
from family_assistant.settings import get_settings


def get_llm() -> LLMClient:
    """Default LLM client. Tests override via app.dependency_overrides.

    `USE_MOCK_LLM=true` in `.env` swaps in the offline mock so the app can
    run without Ollama (UI dev, demo, no-GPU machines).
    """
    if get_settings().use_mock_llm:
        return MockLLMClient()
    return OllamaClient()
