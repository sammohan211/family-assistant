"""Application settings loaded from environment (.env). See .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    app_base_url: str
    cookie_secure: bool = True

    # Which live LLM transport to use: "ollama" (local/self-hosted, the
    # home/GPU deployment) or "openrouter" (cloud, OpenAI-compatible API, for
    # hosts without a GPU). The offline mock is selected separately via
    # use_mock_llm. See ai_gateway/llm.py:default_client.
    llm_provider: str = "ollama"

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"
    # Context window passed to Ollama on every /api/chat call. Default 4096
    # silently truncated real prompts (system + tools + context can hit ~5k).
    # 8192 sized for an 8 GB GPU (RTX 3070): llama3.1:8b Q4 weights ~4.7 GB +
    # ~1 GB KV cache + overhead leaves headroom without spilling layers to CPU.
    # If `llm.prompt_near_ceiling` fires in traces, prefer trimming the context
    # builder (memories cap, current-week-only data) over raising this — each
    # extra 4096 tokens costs ~0.5 GB KV you don't have on this card.
    ollama_num_ctx: int = 8192
    # Swap the live Ollama client for an offline keyword-driven mock. Useful
    # for UI dev on machines without a GPU, and for end-to-end tests that
    # don't want to depend on inference. See ai_gateway/llm_mock.py.
    use_mock_llm: bool = False

    # OpenRouter (cloud) settings — only used when llm_provider="openrouter".
    # Default model mirrors the local llama3.1:8b for behavioural parity; swap
    # for any OpenRouter model that supports JSON `response_format`.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct"
    # Optional app-attribution headers OpenRouter uses for its leaderboard;
    # harmless when unset.
    openrouter_app_url: str | None = None
    openrouter_app_title: str | None = None

    # Horoscope module: precomputed natal-facts file (derived chart facts
    # only, never raw birth data — see scripts/build_natal_facts.py). Lives
    # in the gitignored Data/ directory, mounted read-only in Docker.
    natal_facts_path: str = "Data/natal_facts.json"

    user1_email: str | None = None
    user1_password_hash: str | None = None
    user1_name: str | None = None
    user2_email: str | None = None
    user2_password_hash: str | None = None
    user2_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
