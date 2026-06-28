"""Dependencies for the assistant router (LLM client injection)."""

from family_assistant.ai_gateway.llm import LLMClient, default_client
from family_assistant.ai_gateway.llm_mock import MockLLMClient
from family_assistant.settings import get_settings


def get_llm() -> LLMClient:
    """Default LLM client. Tests override via app.dependency_overrides.

    `USE_MOCK_LLM=true` in `.env` swaps in the offline mock so the app can
    run without inference (UI dev, demo, tests). Otherwise the live provider
    (OpenRouter) is built by `default_client()`.
    """
    if get_settings().use_mock_llm:
        return MockLLMClient()
    return default_client()
