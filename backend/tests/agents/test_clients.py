from __future__ import annotations

from rag_backend.agents.clients import build_clients
from rag_backend.config import Settings

# _env_file=None: these tests pin defaults, independent of the developer's repo-root .env.


def test_default_agents_use_the_local_vision_model_even_when_chat_uses_google() -> None:
    config = Settings(_env_file=None, llm_provider="google")  # type: ignore[call-arg]

    vision, text = build_clients(config)

    assert (vision.provider, vision.model_name) == ("ollama", "qwen2.5vl:3b")
    assert (text.provider, text.model_name) == ("ollama", "qwen2.5vl:3b")


def test_google_vision_uses_its_own_gemini_model_not_the_chat_model() -> None:
    config = Settings(  # type: ignore[call-arg]
        _env_file=None,
        vision_provider="google",
        vision_google_model_name="gemini-flash-latest",
        google_model_name="gemini-flash-lite-latest",
    )

    vision, text = build_clients(config)

    assert (vision.provider, vision.model_name) == ("google", "gemini-flash-latest")
    assert (text.provider, text.model_name) == ("google", "gemini-flash-latest")


def test_text_agents_can_use_a_different_gemini_model() -> None:
    config = Settings(  # type: ignore[call-arg]
        _env_file=None, vision_provider="google", agents_llm_model_name="gemini-2.5-pro"
    )

    _, text = build_clients(config)

    assert (text.provider, text.model_name) == ("google", "gemini-2.5-pro")
