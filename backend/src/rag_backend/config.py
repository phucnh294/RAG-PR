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
    # One JSON file per indexing/retrieval run, under pipeline_log_dir/{indexing,retrieval}/.
    pipeline_log_dir: Path = Path("pipeline-logs")
    max_upload_size_mb: int = 25
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
        "text/markdown",
    )

    llm_base_url: str = "http://llm-model:11434"
    llm_model_name: str = "qwen2.5:0.5b-instruct"
    llm_request_timeout_seconds: float = 60.0

    embedding_base_url: str = "http://embedding-model:11434"
    embedding_request_timeout_seconds: float = 30.0

    chunk_size_words: int = 200
    chunk_overlap_words: int = 20
    embedding_dimension: int = 768
    # Ollama model tag AND the label stored in rag_embeddings.model — identifies which
    # embedding model produced a given vector, so vectors from different models are
    # never silently compared.
    embedding_model_name: str = "nomic-embed-text"

    log_level: str = "INFO"

    retrieval_top_k: int = 5
    # nomic-embed-text's cosine similarity has a much higher "noise floor" than the
    # old hash stub: live testing showed a genuine match scoring ~0.91, but entirely
    # unrelated seeded documents scoring 0.60-0.62 for the same query (short English
    # sentences share substantial embedding-space direction regardless of topic).
    # doc 01's originally-documented 0.5 let those false positives through, so this
    # is set above the observed noise ceiling instead.
    min_similarity_score: float = 0.7

    # Postgres connection. Defaults match .env.example / a local `docker compose up`;
    # postgres_host/port are overridden in docker-compose.yml's backend service to
    # reach the postgres container over the internal Docker network (port 5432 there,
    # not the 5433 host-mapped port used by external tools like DBeaver).
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "db-ai"
    postgres_user: str = "user"
    postgres_password: str = "user"


settings = Settings()
