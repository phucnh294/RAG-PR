"""Per-request context (request id, user id, role) carried in contextvars.

The HTTP middleware in main.py sets request_id; auth.dependencies.get_current_user sets
user_id/role once the caller is resolved. RequestContextFilter copies all three onto
every log record, so each console line can be traced back to one request and one user
(see the format in logging_config.py).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

_NO_VALUE = "-"

request_id_var: ContextVar[str] = ContextVar("request_id", default=_NO_VALUE)
user_id_var: ContextVar[str] = ContextVar("user_id", default=_NO_VALUE)
role_var: ContextVar[str] = ContextVar("role", default=_NO_VALUE)


def set_user_context(user_id: str, role: str) -> None:
    user_id_var.set(user_id)
    role_var.set(role)


class RequestContextFilter(logging.Filter):
    """Attach request_id/user_id/role to every record (never filters anything out)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.role = role_var.get()
        return True
