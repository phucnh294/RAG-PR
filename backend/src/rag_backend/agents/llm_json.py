"""Structured LLM calls for the agents: ask for JSON, validate it against the step's
contract, and log every attempt.

Each attempt is appended to record["steps"][step]["llm_calls"] with the exact messages
sent (images replaced by a size + sha256 placeholder), the raw response, and the parse /
validation errors, so a wrong output can always be traced to the input that caused it.
One repair retry is made on invalid output: the model gets its own answer back together
with the validation errors.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from rag_backend.agents import clients
from rag_backend.agents.run_store import AgentContext
from rag_backend.config import settings
from rag_backend.exceptions import AgentOutputValidationError
from rag_backend.llm_model.client import LlmClient, LlmClientError

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2
_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


def is_transient(error: Exception) -> bool:
    """An overloaded or briefly unreachable provider (429/5xx, dropped connection) is
    worth retrying; a timeout is not (the call already waited its full timeout), nor is
    a 4xx (bad request/key) or anything that isn't an LLM transport failure."""
    if not isinstance(error, LlmClientError):
        return False
    cause = error.__cause__
    if isinstance(cause, httpx.HTTPStatusError):
        return cause.response.status_code in _TRANSIENT_STATUS
    return isinstance(cause, httpx.TransportError) and not isinstance(cause, httpx.TimeoutException)


def extract_json(raw: str) -> Any:
    """Parse the first JSON object in raw, tolerating ```json fences and prose around it
    (small models add both even when asked not to)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in the response")
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(text[start:])
    return value


def prompt_json(value: Any) -> str:
    """JSON for a prompt, without whitespace: every space is a prompt token, and prompt
    processing is the slow part of CPU inference (~7 tokens/s measured)."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _image_placeholder(image_b64: str) -> str:
    data = base64.b64decode(image_b64)
    return f"<image png {len(data)} bytes sha256={hashlib.sha256(data).hexdigest()}>"


def loggable_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loggable = []
    for message in messages:
        entry = dict(message)
        if "images" in entry:
            entry["images"] = [_image_placeholder(image) for image in entry["images"]]
        loggable.append(entry)
    return loggable


def _repair_message(errors: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "Your previous answer was not valid for the required JSON schema:\n"
            f"{errors}\n"
            "Answer again with ONLY the corrected JSON object, no prose and no code fences."
        ),
    }


async def call_structured[ModelT: BaseModel](
    ctx: AgentContext,
    step: str,
    client: LlmClient,
    messages: list[dict[str, Any]],
    model: type[ModelT],
) -> ModelT:
    """Call client, validate the answer as `model`, retrying once with the errors.

    Raises AgentOutputValidationError when both attempts are invalid, and lets
    LlmClientError (model unreachable/timeout) propagate; both are logged first.
    """
    # Both providers constrain generation to the contract's JSON schema (Ollama "format",
    # Gemini "responseJsonSchema"). With only a JSON mime type, Gemini returned objects
    # where the contract wanted strings, even after the repair attempt.
    response_format: dict[str, Any] = model.model_json_schema()
    conversation = list(messages)
    last_error = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        call_log: dict[str, Any] = {
            "attempt": attempt,
            "provider": client.provider,
            "model": client.model_name,
            "response_format": model.__name__,
            "messages": loggable_messages(conversation),
            "raw_response": None,
            "parse_error": None,
            "validation_errors": None,
        }
        raw = await _complete_with_retries(
            ctx, step, client, conversation, response_format, call_log
        )

        try:
            result = model.model_validate(extract_json(raw))
        except ValidationError as error:
            last_error = str(error)
            call_log["validation_errors"] = error.errors(include_url=False, include_input=False)
        except ValueError as error:
            last_error = f"Invalid JSON: {error}"
            call_log["parse_error"] = last_error
        else:
            call_log["valid"] = True
            ctx.recorder.append_extra(step, "llm_calls", call_log)
            ctx.persist()
            return result

        call_log["valid"] = False
        ctx.recorder.append_extra(step, "llm_calls", call_log)
        ctx.persist()
        logger.warning("Agents %s attempt %d invalid output: %s", step, attempt, last_error[:300])
        conversation = [*conversation, {"role": "assistant", "content": raw}]
        conversation.append(_repair_message(last_error))

    raise AgentOutputValidationError(
        f"{step}: output still invalid after {_MAX_ATTEMPTS} attempts: {last_error[:500]}"
    )


async def _complete_with_retries(
    ctx: AgentContext,
    step: str,
    client: LlmClient,
    conversation: list[dict[str, Any]],
    response_format: dict[str, Any] | str,
    call_log: dict[str, Any],
) -> str:
    """One model answer, retrying transient provider errors with backoff. Every failed
    try is logged as its own llm_calls entry (same attempt number, increasing
    "transport_try"), so the log shows exactly what the provider returned and when."""
    retries = max(0, settings.agents_transient_retries)
    for transport_try in range(1, retries + 2):
        started = time.monotonic()
        try:
            raw = await client.complete_chat(
                conversation,
                response_format=response_format,
                options=clients.model_options(),
                fail_on_truncation=True,
            )
        except Exception as error:
            entry = dict(call_log, transport_try=transport_try)
            entry["error"] = f"{type(error).__name__}: {error}"
            entry["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
            retry = transport_try <= retries and is_transient(error)
            delay = settings.agents_retry_backoff_seconds * 2 ** (transport_try - 1)
            if retry:
                entry["retry_in_s"] = delay
            ctx.recorder.append_extra(step, "llm_calls", entry)
            ctx.persist()
            if not retry:
                raise
            logger.warning(
                "Agents %s transient model error, retry in %.0fs: %s", step, delay, error
            )
            await asyncio.sleep(delay)
            continue
        call_log["transport_try"] = transport_try
        call_log["raw_response"] = raw
        call_log["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
        return raw
    raise AssertionError("unreachable: the last try either returns or raises")
