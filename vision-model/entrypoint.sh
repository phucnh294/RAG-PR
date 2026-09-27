#!/bin/sh
set -e

MODEL_NAME="${VISION_MODEL_NAME:-qwen2.5vl:3b}"

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama to be ready..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

echo "Pulling vision model: ${MODEL_NAME}"
ollama pull "${MODEL_NAME}"

wait "${SERVE_PID}"
