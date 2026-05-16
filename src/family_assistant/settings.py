"""Application settings loaded from environment (.env). See .env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    app_base_url: str

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    user1_email: str | None = None
    user1_password_hash: str | None = None
    user2_email: str | None = None
    user2_password_hash: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
