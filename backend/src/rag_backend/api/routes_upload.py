from __future__ import annotations

import hashlib
import shutil

from fastapi import APIRouter, HTTPException, UploadFile

from rag_backend.config import settings
from rag_backend.schemas.documents import DocumentOut, UploadResponse
from rag_backend.storage import dummy_store

router = APIRouter(tags=["documents"])


def _to_document_out(record: dummy_store.DocumentRecord) -> DocumentOut:
    return DocumentOut(
        id=record.id,
        filename=record.filename,
        content_hash=record.content_hash,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        status=record.status,
        created_at=record.created_at,
    )


@router.post("/documents", response_model=UploadResponse)
async def upload_document(file: UploadFile) -> UploadResponse:
    body = await file.read()
    size_mb = len(body) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in settings.allowed_mime_types:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {mime_type}")

    content_hash = hashlib.sha256(body).hexdigest()
    existing = dummy_store.find_by_hash(content_hash)
    if existing is not None:
        return UploadResponse(document=_to_document_out(existing), already_exists=True)

    record = dummy_store.add_document(
        filename=file.filename or "untitled",
        content_hash=content_hash,
        mime_type=mime_type,
        size_bytes=len(body),
        excerpts=[body.decode("utf-8", errors="ignore")[:200]] if body else [],
    )

    doc_dir = settings.input_dir / record.id
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / record.filename).write_bytes(body)

    return UploadResponse(document=_to_document_out(record), already_exists=False)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents() -> list[DocumentOut]:
    return [_to_document_out(record) for record in dummy_store.list_documents()]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str) -> None:
    if dummy_store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    dummy_store.delete_document(document_id)
    doc_dir = settings.input_dir / document_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)
