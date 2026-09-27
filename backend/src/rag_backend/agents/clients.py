"""Model clients used by the agents. Module-level instances (like guardrails.judge_client),
so tests swap them with monkeypatch.setattr(clients, "vision_client", ...). Callers must
use clients.vision_client (attribute access), never `from ... import vision_client`."""

from __future__ import annotations

from rag_backend.config import Settings, settings
from rag_backend.llm_model.client import LlmClient


def build_clients(config: Settings) -> tuple[LlmClient, LlmClient]:
    """(vision client, text client). The text agents default to the vision provider and
    model; with provider "google" both use GOOGLE_API_KEY and vision_google_model_name."""
    vision = LlmClient(
        base_url=config.vision_base_url,
        model_name=config.vision_model_name,
        provider=config.vision_provider,
        google_model_name=config.vision_google_model_name,
        request_timeout_seconds=config.vision_request_timeout_seconds,
    )
    text_provider = config.agents_llm_provider or config.vision_provider
    text = LlmClient(
        base_url=config.agents_llm_base_url or config.vision_base_url,
        model_name=config.agents_llm_model_name or config.vision_model_name,
        provider=text_provider,
        google_model_name=config.agents_llm_model_name or config.vision_google_model_name,
        request_timeout_seconds=config.agents_llm_timeout_seconds,
    )
    return vision, text


vision_client, agents_text_client = build_clients(settings)


def model_options() -> dict[str, float | int]:
    """Ollama options for every agent call: a context window large enough for the
    prompts, temperature 0 so reruns of the same input are comparable, and a cap on the
    answer length."""
    return {
        "num_ctx": settings.agents_num_ctx,
        "temperature": settings.agents_temperature,
        "num_predict": settings.agents_num_predict,
    }
