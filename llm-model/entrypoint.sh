#!/bin/sh
set -e

MODEL_NAME="${LLM_MODEL_NAME:-qwen2.5:0.5b-instruct}"

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama to be ready..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

echo "Pulling LLM model: ${MODEL_NAME}"
ollama pull "${MODEL_NAME}"

wait "${SERVE_PID}"
