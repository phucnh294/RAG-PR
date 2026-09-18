from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    input_dir: Path = Path("data/input")
    max_upload_size_mb: int = 25
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
        "text/markdown",
    )


settings = Settings()
