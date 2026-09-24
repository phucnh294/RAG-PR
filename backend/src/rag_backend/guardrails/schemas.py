from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GuardrailVerdict(BaseModel):
    """Outcome of one guardrail check (Layer 1 input or Layer 3 output)."""

    layer: Literal["input", "output"]
    verdict: Literal["safe", "unsafe", "judge_error"]
    reason: str
    category: str | None = None


# A verdict is treated as blocked whether the judge actively flagged it ("unsafe") or
# the judge itself failed/returned unparsable output ("judge_error") — fail-closed.
BLOCKED_VERDICTS: set[str] = {"unsafe", "judge_error"}


class EvidenceSummary(BaseModel):
    """Layer 2 flag-only signal describing how well retrieved chunks support an answer."""

    level: Literal["high", "medium", "low", "none"]
    top_score: float | None
    mean_score: float | None
    surviving_chunk_count: int
    threshold: float
