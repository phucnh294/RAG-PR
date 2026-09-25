from __future__ import annotations

import hashlib
import logging
import shutil
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile

from rag_backend.auth import service as auth_service
from rag_backend.auth.dependencies import CurrentUserDep
from rag_backend.auth.models import CurrentUser
from rag_backend.config import settings
from rag_backend.db import postgres_store
from rag_backend.rag_pipeline.indexing.frontmatter import classification_hint
from rag_backend.rag_pipeline.indexing.pipeline import run_indexing
from rag_backend.schemas.documents import DocumentOut, UploadResponse
from rag_backend.semantic_cache import service as semantic_cache_service
from rag_backend.storage.records import DocumentRecord

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


def _to_document_out(record: DocumentRecord, user: CurrentUser) -> DocumentOut:
    return DocumentOut(
        id=record.id,
        filename=record.filename,
        content_hash=record.content_hash,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        status=record.status,
        created_at=record.created_at,
        classification=record.classification,
        tags=record.tags,
        created_by=record.created_by,
        created_by_username=record.created_by_username,
        can_delete=auth_service.can_delete(user, record),
    )


def _parse_tags(raw: str | None) -> list[str]:
    tags = [tag.strip() for tag in (raw or "").split(",")]
    return list(dict.fromkeys(tag for tag in tags if tag))


@router.post("/documents", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: CurrentUserDep,
    classification: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(description="Comma-separated tags")] = None,
) -> UploadResponse:
    """Upload and index a document.

    classification: explicit choice, else the markdown frontmatter's `classification:`,
    else the configured default (capped at the caller's clearance). 403 above clearance.
    Dedup key is (classification, content hash, uploader): the same bytes uploaded again by
    the same user into the same classification return the existing document and are not
    re-indexed; any other combination is a new document.
    """
    body = await file.read()
    size_mb = len(body) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in settings.allowed_mime_types:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {mime_type}")

    resolved_classification = await auth_service.resolve_upload_classification(
        user, classification, classification_hint(body, mime_type)
    )
    content_hash = hashlib.sha256(body).hexdigest()
    existing = await postgres_store.find_existing(resolved_classification, content_hash, user.id)
    if existing is not None:
        logger.info(
            "Upload skipped (already indexed): document=%s classification=%s hash=%s",
            existing.id,
            resolved_classification,
            content_hash[:12],
        )
        return UploadResponse(document=_to_document_out(existing, user), already_exists=True)

    record = await postgres_store.add_document(
        filename=file.filename or "untitled",
        content_hash=content_hash,
        mime_type=mime_type,
        size_bytes=len(body),
        classification=resolved_classification,
        created_by=user.id,
        tags=_parse_tags(tags),
    )
    # created_by_username is only filled by the permission view; the uploader is the caller.
    record.created_by_username = user.username
    logger.info(
        "Upload accepted: document=%s file=%s classification=%s tags=%s hash=%s",
        record.id,
        record.filename,
        record.classification,
        record.tags,
        content_hash[:12],
    )

    doc_dir = settings.input_dir / record.id
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / record.filename).write_bytes(body)

    background_tasks.add_task(run_indexing, record.id, record.filename, record.mime_type)

    return UploadResponse(document=_to_document_out(record, user), already_exists=False)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(user: CurrentUserDep) -> list[DocumentOut]:
    """Only the documents whose classification the caller's role may read."""
    return [
        _to_document_out(record, user) for record in await postgres_store.list_documents(user.id)
    ]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, user: CurrentUserDep) -> DocumentOut:
    record = await postgres_store.get_document(document_id, user.id)
    if record is None:
        # Same 404 whether it doesn't exist or isn't readable: never confirm existence.
        raise HTTPException(status_code=404, detail="Document not found")
    return _to_document_out(record, user)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, user: CurrentUserDep) -> None:
    record = await postgres_store.get_document(document_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not auth_service.can_delete(user, record):
        auth_service.audit_denied(user, "delete_document", document_id, "not creator or admin")
        raise HTTPException(
            status_code=403, detail="Only the document's creator or an admin can delete it"
        )
    await postgres_store.delete_document(document_id)
    await semantic_cache_service.invalidate_document(document_id)
    doc_dir = settings.input_dir / document_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)
    logger.info("Document deleted: document=%s file=%s", document_id, record.filename)
