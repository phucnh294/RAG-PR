from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://192.168.1.69:3000",
    ]
    input_dir: Path = Path("data/input")
    max_upload_size_mb: int = 25
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
        "text/markdown",
    )

    llm_base_url: str = "http://llm-model:11434"
    llm_model_name: str = "qwen2.5:0.5b-instruct"
    llm_request_timeout_seconds: float = 60.0

    chunk_size_words: int = 200
    chunk_overlap_words: int = 20
    embedding_dimension: int = 768

    log_level: str = "INFO"

    retrieval_top_k: int = 5
    # Tuned for the stub bag-of-words embedding (see embedding_model/client.py) — will
    # need recalibrating once a real embedding-model container replaces the stub.
    min_similarity_score: float = 0.3


settings = Settings()
