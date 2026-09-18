from __future__ import annotations

import logging

from rag_backend.config import settings


def configure_logging() -> None:
    """Set up root logging so INFO-level pipeline logs (step timing, system prompt) are
    actually emitted. force=True overrides any handlers uvicorn already attached.
    """
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
