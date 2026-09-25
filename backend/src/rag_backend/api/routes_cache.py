from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from rag_backend.auth.dependencies import AdminUserDep
from rag_backend.exceptions import SemanticCacheError
from rag_backend.schemas.conversations import CacheClearedOut
from rag_backend.semantic_cache import service as semantic_cache_service

router = APIRouter(prefix="/cache", tags=["cache"])
logger = logging.getLogger(__name__)


@router.delete("", response_model=CacheClearedOut)
async def clear_cache(user: AdminUserDep) -> CacheClearedOut:
    """Admin-only: drop every semantic cache entry (e.g. after changing prompts)."""
    try:
        deleted = await semantic_cache_service.clear()
    except SemanticCacheError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    logger.info("Semantic cache cleared by %s: %d entries", user.username, deleted)
    return CacheClearedOut(deleted=deleted)
