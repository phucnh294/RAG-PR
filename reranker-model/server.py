"""Cross-encoder reranking service: a drop-in for text-embeddings-inference's /rerank.

Serves cross-encoder/ms-marco-MiniLM-L6-v2 through ONNX Runtime on CPU. It keeps TEI's
request/response contract, so the backend's RerankerClient works unchanged against
either this image or the official TEI image:

    POST /rerank {"query": str, "texts": [str], "raw_scores": bool, "truncate": bool}
      -> [{"index": int, "score": float}, ...] sorted by score, highest first
    GET  /health -> 200 once the model is loaded
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from tokenizers import Tokenizer

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("reranker")

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/model"))
MODEL_ID = os.environ.get("MODEL_ID", "cross-encoder/ms-marco-MiniLM-L6-v2")
# Same limit TEI enforces by default (--max-client-batch-size); the backend batches to it.
MAX_CLIENT_BATCH_SIZE = int(os.environ.get("MAX_CLIENT_BATCH_SIZE", "32"))
# BERT's position-embedding limit: longer (question, passage) pairs must be truncated.
MAX_INPUT_TOKENS = 512


class RerankRequest(BaseModel):
    query: str
    texts: list[str] = Field(min_length=1)
    raw_scores: bool = False
    truncate: bool = True


class RerankResult(BaseModel):
    index: int
    score: float


class CrossEncoder:
    """Scores (query, passage) pairs with the ONNX export of the cross-encoder."""

    def __init__(self, model_dir: Path) -> None:
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        threads = int(os.environ.get("ORT_INTRA_OP_THREADS", "0"))  # 0 = ONNX Runtime picks
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {model_input.name for model_input in self._session.get_inputs()}

    def logits(self, query: str, texts: list[str], truncate: bool) -> list[float]:
        if truncate:
            self._tokenizer.enable_truncation(max_length=MAX_INPUT_TOKENS)
        else:
            self._tokenizer.no_truncation()
        encodings = self._tokenizer.encode_batch([(query, text) for text in texts])
        if not truncate and any(len(encoding.ids) > MAX_INPUT_TOKENS for encoding in encodings):
            raise ValueError(f"input exceeds {MAX_INPUT_TOKENS} tokens and truncate=false")
        feed = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
        }
        outputs = self._session.run(
            None, {name: value for name, value in feed.items() if name in self._input_names}
        )
        return [float(value) for value in outputs[0][:, 0]]


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


app = FastAPI(title="reranker-model")
_model = CrossEncoder(MODEL_DIR)
logger.info("Loaded %s from %s", MODEL_ID, MODEL_DIR)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_ID}


@app.post("/rerank", response_model=list[RerankResult])
def rerank(request: RerankRequest) -> list[RerankResult]:
    """Sync handler on purpose: FastAPI runs it in its threadpool, and ONNX Runtime
    releases the GIL during inference, so the event loop is never blocked."""
    if len(request.texts) > MAX_CLIENT_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"batch size {len(request.texts)} > maximum {MAX_CLIENT_BATCH_SIZE}",
        )
    try:
        logits = _model.logits(request.query, request.texts, request.truncate)
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    scores = logits if request.raw_scores else [_sigmoid(value) for value in logits]
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    return [RerankResult(index=index, score=score) for index, score in ranked]
