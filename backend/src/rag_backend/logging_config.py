from __future__ import annotations

import logging

from rag_backend.config import settings
from rag_backend.request_context import RequestContextFilter

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s [req=%(request_id)s user=%(user_id)s role=%(role)s] "
    "%(name)s: %(message)s"
)


def configure_logging() -> None:
    """Set up root logging so INFO-level pipeline logs (step timing, system prompt) are
    actually emitted. force=True overrides any handlers uvicorn already attached.

    The context filter sits on the handler (not a logger) so records from every logger,
    including uvicorn's and third-party ones, get the request/user fields the format needs.
    """
    logging.basicConfig(level=settings.log_level, format=_LOG_FORMAT, force=True)
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestContextFilter())
