from __future__ import annotations

from fastapi import APIRouter

from rag_backend.auth.dependencies import AdminUserDep
from rag_backend.eval.rerank_comparison import run_rerank_comparison
from rag_backend.eval.runner import run_golden_set
from rag_backend.eval.schemas import EvalReport, RerankComparisonReport

router = APIRouter(prefix="/eval", tags=["eval"])


@router.post("/run", response_model=EvalReport)
async def run_eval(admin: AdminUserDep) -> EvalReport:
    """Run the golden set against the currently configured LLM/judge and return metrics.

    A POST, not a GET: this has real cost/latency (one LLM + judge round trip per
    golden-set entry), unlike the read-only inspection endpoints in routes_logs.py.
    Admin only, for the same reason.
    """
    return await run_golden_set(admin)


@router.post("/rerank-comparison", response_model=RerankComparisonReport)
async def rerank_comparison(admin: AdminUserDep) -> RerankComparisonReport:
    """Score the golden set's retrieval twice over the same candidate pool — hybrid order
    vs cross-encoder order — and return both arms' recall/MRR/nDCG plus the deltas.

    No LLM calls (retrieval only), but it does call the reranker once per query, so it
    is a POST and admin-only like /eval/run.
    """
    return await run_rerank_comparison(admin)
