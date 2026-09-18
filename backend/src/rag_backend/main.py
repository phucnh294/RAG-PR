from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag_backend.api import routes_chat, routes_health, routes_upload
from rag_backend.config import settings
from rag_backend.storage import dummy_store


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    dummy_store.seed()
    yield


def create_app() -> FastAPI:
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
    return app


app = create_app()
