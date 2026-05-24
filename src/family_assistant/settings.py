"""Application settings loaded from environment (.env). See .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    app_base_url: str
    cookie_secure: bool = True

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"
    # Context window passed to Ollama on every /api/chat call. Default 4096
    # silently truncated real prompts (system + tools + context can hit ~5k);
    # 8192 gives headroom on llama3.1:8b without measurable latency cost.
    ollama_num_ctx: int = 8192
    # Swap the live Ollama client for an offline keyword-driven mock. Useful
    # for UI dev on machines without a GPU, and for end-to-end tests that
    # don't want to depend on inference. See ai_gateway/llm_mock.py.
    use_mock_llm: bool = False

    user1_email: str | None = None
    user1_password_hash: str | None = None
    user1_name: str | None = None
    user2_email: str | None = None
    user2_password_hash: str | None = None
    user2_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
