from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rag_backend.api import (
    routes_auth,
    routes_cache,
    routes_chat,
    routes_conversations,
    routes_eval,
    routes_health,
    routes_logs,
    routes_upload,
)
from rag_backend.api.routes_chat import CONVERSATION_ID_HEADER
from rag_backend.auth import seed as auth_seed
from rag_backend.config import settings
from rag_backend.db import authz_schema, chat_schema, postgres_store
from rag_backend.db import session as db_session
from rag_backend.exceptions import (
    AuthError,
    ConversationNotFoundError,
    InactiveUserError,
    InvalidClassificationError,
    InvalidRoleError,
    PermissionDeniedError,
    UnknownUserError,
    UserAlreadyExistsError,
)
from rag_backend.logging_config import configure_logging
from rag_backend.request_context import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

_AUTH_ERROR_STATUS: dict[type[AuthError], int] = {
    UnknownUserError: 401,
    InactiveUserError: 403,
    PermissionDeniedError: 403,
    UserAlreadyExistsError: 409,
    InvalidRoleError: 422,
    InvalidClassificationError: 422,
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # db_session.init_pool (not a from-import) so tests can monkeypatch it away.
    await db_session.init_pool()
    await postgres_store.ensure_fulltext_index()
    await authz_schema.ensure_authorization_schema()
    await chat_schema.ensure_chat_schema()
    admin = await auth_seed.bootstrap_authorization()
    await authz_schema.finalize_document_ownership(admin.id, settings.auth_default_classification)
    await postgres_store.seed(admin.id)
    logger.info("Startup complete")
    yield
    await db_session.close_pool()


async def _handle_auth_error(request: Request, error: Exception) -> JSONResponse:
    status = next(
        (code for kind, code in _AUTH_ERROR_STATUS.items() if isinstance(error, kind)), 403
    )
    logger.warning(
        "AUTH error path=%s status=%d %s: %s",
        request.url.path,
        status,
        type(error).__name__,
        error,
    )
    return JSONResponse(status_code=status, content={"detail": str(error)})


async def _handle_conversation_not_found(request: Request, error: Exception) -> JSONResponse:
    logger.info("Conversation not found path=%s: %s", request.url.path, error)
    return JSONResponse(status_code=404, content={"detail": "Conversation not found"})


async def _log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """One access-log line per request, tagged with a request id the client can quote.

    Honors an incoming X-Request-ID (so a caller can correlate across services) and echoes
    it back. The user/role come from request.state, set by auth.get_current_user.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    started = time.monotonic()
    try:
        response = await call_next(request)
        # The user was resolved in the endpoint's task, so its contextvars didn't flow
        # back here; request.state carries it instead.
        user = getattr(request.state, "user", None)
        logger.info(
            "HTTP %s %s -> %d in %.1fms user=%s role=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - started) * 1000,
            user.username if user is not None else "-",
            user.role if user is not None else "-",
        )
    except Exception:
        logger.exception("HTTP %s %s failed", request.method, request.url.path)
        raise
    finally:
        request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="RAG Backend", lifespan=lifespan)

    app.middleware("http")(_log_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER, CONVERSATION_ID_HEADER],
    )
    app.add_exception_handler(AuthError, _handle_auth_error)
    app.add_exception_handler(ConversationNotFoundError, _handle_conversation_not_found)

    # Every router except health and auth resolves the caller through
    # auth.dependencies.get_current_user inside its handlers (401 without X-User-Id).
    app.include_router(routes_health.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_upload.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_cache.router)
    app.include_router(routes_logs.router)
    app.include_router(routes_eval.router)
    return app


app = create_app()
