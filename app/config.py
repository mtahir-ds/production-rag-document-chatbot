"""Centralized configuration settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated via Pydantic and sourced from `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = Field(default="Production RAG Service")
    app_env: Literal["development", "staging", "production", "test"] = Field(
        default="development"
    )
    app_version: str = Field(default="0.1.0")
    log_level: str = Field(default="INFO")
    app_debug: bool = Field(default=False)

    # --- Google Gemini API ---
    gemini_api_key: str = Field(default="")
    gemini_llm_model: str = Field(default="gemini-2.5-flash")
    gemini_embedding_model: str = Field(default="gemini-embedding-001")
    embedding_dimensions: int = Field(default=1536, ge=128, le=3072)

    # --- Qdrant Vector Database ---
    qdrant_mode: Literal["local", "cloud"] = Field(default="local")
    qdrant_path: str = Field(default="./qdrant_storage")
    qdrant_url: str = Field(default="")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="rag_documents")

    # --- Local Persistence ---
    sqlite_db_path: str = Field(default="./data/rag_service.db")
    upload_dir: str = Field(default="./uploads")

    # --- Ingestion & Chunking ---
    max_file_size_mb: int = Field(default=20, ge=1, le=100)
    max_pdf_pages: int = Field(default=200, ge=1, le=2000)
    chunk_size_tokens: int = Field(default=500, ge=100, le=2000)
    chunk_overlap_tokens: int = Field(default=80, ge=0, le=500)

    # --- Retrieval & Generation ---
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    max_question_length: int = Field(default=1000, ge=50, le=5000)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)

    # --- Reliability & Rate Limiting ---
    api_timeout_seconds: int = Field(default=30, ge=5, le=120)
    api_max_retries: int = Field(default=2, ge=0, le=5)
    rate_limit_ask: str = Field(default="20/minute")
    rate_limit_upload: str = Field(default="10/minute")

    # --- JWT Authentication (Bonus B1) ---
    enable_auth: bool = Field(default=True)
    jwt_secret_key: str = Field(default="dev-insecure-secret-change-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440, ge=5, le=43200)

    @property
    def max_file_size_bytes(self) -> int:
        """Return the maximum upload size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Create required local storage directories if they do not exist."""
        Path(self.sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        if self.qdrant_mode == "local":
            Path(self.qdrant_path).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
