from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env (backend/src/rag_backend/config.py -> backend -> repo root), resolved
# from this file's location rather than the process CWD. Docker Compose injects env vars
# directly and doesn't need this file, but running the backend locally (e.g. `uvicorn`
# from backend/) would otherwise miss the root .env depending on where it's launched from.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Runtime configuration. Every field below can be overridden via an environment
    variable of the same name (case-insensitive) or by setting it in the repo-root
    `.env` file — see `.env.example` for the full list. No code changes are needed to
    point at a different LLM, embedding model, port, or database.
    """

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

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

    # "ollama" uses the local llm-model container's /api/chat endpoint below;
    # "google" calls the Gemini API instead and requires google_api_key.
    llm_provider: str = "ollama"
    llm_base_url: str = "http://llm-model:11434"
    llm_model_name: str = "qwen2.5:0.5b-instruct"
    llm_request_timeout_seconds: float = 60.0

    google_api_key: str | None = None
    google_model_name: str = "gemini-2.0-flash"

    embedding_base_url: str = "http://embedding-model:11434"
    # Per /api/embed request, i.e. per batch below — not per document.
    embedding_request_timeout_seconds: float = 60.0
    # Chunks per /api/embed request. On CPU Ollama a 21-chunk request took ~33s
    # (measured), so whole-document requests timed out and left documents with no chunks.
    embedding_batch_size: int = 8

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

    # Hybrid search: pgvector cosine search + Postgres full-text search over
    # rag_chunks.content_tsv, fused with Reciprocal Rank Fusion (score = sum of
    # 1 / (rrf_k + rank) across both result lists). Each retriever returns up to
    # hybrid_candidate_k candidates; the fused list is then cut to retrieval_top_k.
    # When disabled, step 4 falls back to pure vector search.
    hybrid_search_enabled: bool = True
    hybrid_candidate_k: int = 20
    rrf_k: int = 60
    # Postgres text search configuration (regconfig) used both to build content_tsv at
    # indexing time and to parse the query. Changing it only affects newly indexed
    # chunks — re-index (or NULL out content_tsv and restart) to rebuild old ones.
    fulltext_search_config: str = "english"

    # Postgres connection. Defaults match .env.example / a local `docker compose up`;
    # postgres_host/port are overridden in docker-compose.yml's backend service to
    # reach the postgres container over the internal Docker network (port 5432 there,
    # not the 5433 host-mapped port used by external tools like DBeaver).
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "db-ai"
    postgres_user: str = "user"
    postgres_password: str = "user"

    # --- Guardrails ---
    guardrail_input_enabled: bool = True
    guardrail_output_enabled: bool = True
    # Layer 2 (evidence) is always flag-only — this toggle only controls whether the
    # signal is computed; it can never block the LLM call.
    guardrail_evidence_enabled: bool = True
    guardrail_max_input_chars: int = 4000
    # The judge LLM falls back to the main answer LLM's provider/model/base_url when
    # unset, so guardrails work out of the box with zero extra config. Override these
    # to point the judge at a cheaper/faster model in production.
    guardrail_judge_provider: str | None = None
    guardrail_judge_base_url: str | None = None
    guardrail_judge_model_name: str | None = None
    guardrail_judge_timeout_seconds: float = 20.0
    # Evidence buckets for Layer 2, computed from the same cosine scores as
    # min_similarity_score above: >= high -> "high", >= medium -> "medium",
    # >= min_similarity_score -> "low", otherwise (no surviving chunks) -> "none".
    guardrail_evidence_high_threshold: float = 0.85
    guardrail_evidence_medium_threshold: float = 0.75
    guardrail_refusal_message: str = "I can't help with that request."


settings = Settings()
