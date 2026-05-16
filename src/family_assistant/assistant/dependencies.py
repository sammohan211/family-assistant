"""Dependencies for the assistant router (LLM client injection)."""

from family_assistant.ai_gateway.llm import LLMClient, OllamaClient


def get_llm() -> LLMClient:
    """Default LLM client. Tests override via app.dependency_overrides."""
    return OllamaClient()
