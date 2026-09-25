from __future__ import annotations

from fastapi import APIRouter

from rag_backend.eval.runner import run_golden_set
from rag_backend.eval.schemas import EvalReport

router = APIRouter(prefix="/eval", tags=["eval"])


@router.post("/run", response_model=EvalReport)
async def run_eval() -> EvalReport:
    """Run the golden set against the currently configured LLM/judge and return metrics.

    A POST, not a GET: this has real cost/latency (one LLM + judge round trip per
    golden-set entry), unlike the read-only inspection endpoints in routes_logs.py.
    """
    return await run_golden_set()
