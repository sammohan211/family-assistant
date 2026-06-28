"""Application settings loaded from environment (.env). See .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    app_base_url: str
    cookie_secure: bool = True

    # Which live LLM transport to use. Only "openrouter" (cloud, OpenAI-
    # compatible API) is supported. The offline mock is selected separately
    # via use_mock_llm. See ai_gateway/llm.py:default_client.
    llm_provider: str = "openrouter"

    # Swap the live client for an offline keyword-driven mock. Useful for UI
    # dev without hitting a real provider, and for end-to-end tests that don't
    # want to depend on inference. See ai_gateway/llm_mock.py.
    use_mock_llm: bool = False

    # OpenRouter (cloud) settings. Swap the model for any OpenRouter model that
    # supports JSON `response_format`.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct"
    # Optional app-attribution headers OpenRouter uses for its leaderboard;
    # harmless when unset.
    openrouter_app_url: str | None = None
    openrouter_app_title: str | None = None

    user1_email: str | None = None
    user1_password_hash: str | None = None
    user1_name: str | None = None
    user2_email: str | None = None
    user2_password_hash: str | None = None
    user2_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
