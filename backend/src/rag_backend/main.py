from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_backend.api import routes_chat, routes_eval, routes_health, routes_logs, routes_upload
from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.db.session import close_pool, init_pool
from rag_backend.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    await postgres_store.seed()
    yield
    await close_pool()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="RAG Backend (dummy)", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_health.router)
    app.include_router(routes_upload.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_logs.router)
    app.include_router(routes_eval.router)
    return app


app = create_app()
