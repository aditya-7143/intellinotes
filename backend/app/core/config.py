from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )

    APP_NAME: str = "IntelliNotes"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/intellinotes"
    DATABASE_ECHO: bool = False

    JWT_SECRET: str = "secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    LLM_PROVIDER: Literal["ollama", "openai", "anthropic", "openrouter"] = "openrouter"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "openrouter/auto"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Embeddings are local and independent of the chat LLM provider.
    EMBEDDING_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    RAG_TOP_K: int = Field(default=5, ge=1, le=20)
    RAG_MIN_SIMILARITY: float = Field(default=0.3, ge=0, le=1)
    RAG_INDEX_MAX_ATTEMPTS: int = Field(default=8, ge=1, le=100)

    STORAGE_TYPE: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_PATH: str = "./data/notes"
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_REGION: str = "us-east-1"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
