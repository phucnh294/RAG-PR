# Cross-encoder reranker (ms-marco-MiniLM-L6-v2) served over a TEI-compatible /rerank API.
#
# Built from Docker Hub's python image with ONNX Runtime instead of the official
# ghcr.io/huggingface/text-embeddings-inference image: on this project's dev machine the
# ghcr.io pull is refused by Docker Desktop's registry proxy ("denied"). The API contract
# is the same, so switching back to TEI later only means changing this Dockerfile and the
# port in docker-compose.yml.
FROM python:3.12-slim

# Pinned model revision so every build serves byte-identical weights.
ARG MODEL_REPO=cross-encoder/ms-marco-MiniLM-L6-v2
ARG MODEL_REVISION=233902d25c440f23af6f7d6e94d2946bac0bee0a

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/model \
    MODEL_ID=${MODEL_REPO}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the model into the image (~90 MB): the container starts ready, with no runtime
# download and no volume to keep in sync with the pinned revision.
RUN python -c "import sys, urllib.request; from pathlib import Path; \
base = f'https://huggingface.co/{sys.argv[1]}/resolve/{sys.argv[2]}'; \
Path('/model').mkdir(); \
[urllib.request.urlretrieve(f'{base}/{src}', f'/model/{dst}') \
 for src, dst in (('onnx/model.onnx', 'model.onnx'), ('tokenizer.json', 'tokenizer.json'))]" \
    "${MODEL_REPO}" "${MODEL_REVISION}"

COPY server.py .

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
