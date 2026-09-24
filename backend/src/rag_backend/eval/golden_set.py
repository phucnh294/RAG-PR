from __future__ import annotations

import json
from pathlib import Path

from rag_backend.eval.schemas import GoldenEntry

_DEFAULT_PATH = Path(__file__).parent / "golden_set.json"


def load_golden_set(path: Path | None = None) -> list[GoldenEntry]:
    """Load and validate the golden-set query list from JSON."""
    raw = json.loads((path or _DEFAULT_PATH).read_text(encoding="utf-8"))
    return [GoldenEntry.model_validate(entry) for entry in raw]
