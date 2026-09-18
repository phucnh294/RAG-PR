from __future__ import annotations

from dataclasses import dataclass

from rag_backend.config import settings


@dataclass
class LoadedFile:
    document_id: str
    filename: str
    mime_type: str
    raw_bytes: bytes


def load_input(document_id: str, filename: str, mime_type: str) -> LoadedFile:
    """Read the raw bytes already saved under data/input/<document_id>/<filename> by the upload route."""
    file_path = settings.input_dir / document_id / filename
    raw_bytes = file_path.read_bytes()
    return LoadedFile(
        document_id=document_id,
        filename=filename,
        mime_type=mime_type,
        raw_bytes=raw_bytes,
    )
