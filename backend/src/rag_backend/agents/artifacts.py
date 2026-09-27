"""Files a run produces (screenshots, evidence, the generated .spec.ts), saved inside the
run folder (see run_layout.py) and referenced from the JSON log by ArtifactRef, so the log
stays readable JSON with no base64 blobs. ArtifactRef.name is the path relative to the
run folder, e.g. "test-cases/TC-REG-001/evidence/step-03-click.png"."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from rag_backend.agents.run_layout import agents_root, is_safe_relative
from rag_backend.agents.schemas import ArtifactRef

SERVABLE_SUFFIXES = frozenset({".png", ".ts", ".md", ".json", ".txt"})


def save_bytes(root: Path, rel: str, data: bytes) -> ArtifactRef:
    if not is_safe_relative(rel):
        raise ValueError(f"Unsafe artifact path: {rel!r}")
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return ArtifactRef(name=rel, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def save_png_b64(root: Path, rel: str, png_b64: str) -> ArtifactRef:
    return save_bytes(root, rel, base64.b64decode(png_b64))


def save_text(root: Path, rel: str, text: str) -> ArtifactRef:
    return save_bytes(root, rel, text.encode("utf-8"))


def resolve(root: Path, rel: str) -> Path | None:
    """The file for a run-relative path, or None when the path is unsafe, not a servable
    type, outside the run folder, or missing."""
    if not is_safe_relative(rel) or Path(rel).suffix not in SERVABLE_SUFFIXES:
        return None
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return None
    return path


def legacy_root(run_id: str) -> Path:
    """Runs written before the per-run folder layout kept files in agents/artifacts/{id}."""
    return agents_root() / "artifacts" / run_id
