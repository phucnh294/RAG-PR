# Small vision-language model (default qwen2.5vl:3b) for the Agents pipeline's UI-analysis
# agent — same Ollama pattern as llm-model/. qwen2.5vl needs Ollama >= 0.7.
FROM ollama/ollama:latest

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
