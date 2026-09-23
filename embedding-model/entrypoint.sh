#!/bin/sh
set -e

MODEL_NAME="${EMBEDDING_MODEL_NAME:-nomic-embed-text}"

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama to be ready..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

echo "Pulling embedding model: ${MODEL_NAME}"
ollama pull "${MODEL_NAME}"

wait "${SERVE_PID}"
