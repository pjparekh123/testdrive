"""The one LLM wrapper. Every LLM call in the codebase goes through here.

Single entrypoint::

    await call(prompt_name, variables, response_model, model) -> response_model

Responsibilities (§5 hard requirement, §13 failure modes):
  * load ``prompts/{prompt_name}.md`` and format it with ``variables``
  * call the Anthropic SDK, parse JSON, validate against ``response_model``
  * on JSON/schema failure: retry once with an appended stricter nudge, then
    hard-fail (``LLMError``)
  * on rate-limit / 5xx: exponential backoff 2s, 8s, 30s; max 3 tries
  * log every call: prompt name, model, latency, input/output tokens, cost
  * track cost against a hard monthly cap (§18)

No raw Anthropic SDK calls live anywhere else.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from . import prompts as prompt_lib
from .config import get_settings
from .logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)

# Approximate USD per 1M tokens (input, output). Used for the cost ledger only.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
_BACKOFF_SCHEDULE = (2.0, 8.0, 30.0)  # §13: 2s, 8s, 30s; max 3 tries
_JSON_NUDGE = (
    "Your previous output was not valid JSON. Return only the JSON object, "
    "with no prose and no markdown fences."
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(RuntimeError):
    """Raised when the wrapper cannot return a validated response."""


class CostCapExceeded(LLMError):
    """Raised when a call would push spend over the monthly cap."""


# --- cost tracking ----------------------------------------------------------


class CostTracker:
    def __init__(self, cap_usd: float) -> None:
        self.cap_usd = cap_usd
        self.spent_usd = 0.0

    def cost_of(self, model: str, in_tokens: int, out_tokens: int) -> float:
        pin, pout = _PRICING.get(model, (0.0, 0.0))
        return (in_tokens / 1_000_000) * pin + (out_tokens / 1_000_000) * pout

    def would_exceed(self) -> bool:
        return self.spent_usd >= self.cap_usd

    def record(self, model: str, in_tokens: int, out_tokens: int) -> float:
        cost = self.cost_of(model, in_tokens, out_tokens)
        self.spent_usd += cost
        return cost


@lru_cache(maxsize=1)
def _cost_conn():
    """A dedicated connection for the cost ledger (used during enrichment, when
    the caller's connection is idle). Degrades to None if the DB is unavailable."""
    from . import db

    try:
        return db.get_conn()
    except Exception:  # pragma: no cover - DB optional for cost tracking
        return None


@lru_cache(maxsize=1)
def _cost_tracker() -> CostTracker:
    tracker = CostTracker(get_settings().monthly_cost_cap_usd)
    # Seed in-process spend from the persisted monthly total so the cap holds
    # across separate processes (CLI runs, bot restarts).
    from . import db

    conn = _cost_conn()
    if conn is not None:
        try:
            tracker.spent_usd = db.get_month_spend(conn)
        except Exception:
            pass
    return tracker


def _persist_cost(cost: float) -> None:
    from . import db

    conn = _cost_conn()
    if conn is None:
        return
    try:
        db.add_month_spend(conn, cost)
    except Exception as e:  # never let cost bookkeeping break enrichment
        log.warning("llm.cost_persist_failed", error=str(e)[:120])


@lru_cache(maxsize=1)
def _client():
    from anthropic import AsyncAnthropic

    # max_retries=0: this wrapper owns retry/backoff so behaviour is explicit
    # and deterministic under VCR.
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key, max_retries=0)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of model text, tolerating markdown fences."""
    candidate = text.strip()
    m = _FENCE_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]
    return json.loads(candidate)


# --- the entrypoint ---------------------------------------------------------


async def call(
    prompt_name: str,
    variables: dict,
    response_model: type[T],
    model: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> T:
    """Run one prompt and return a validated ``response_model`` instance."""
    tracker = _cost_tracker()
    if tracker.would_exceed():
        raise CostCapExceeded(
            f"monthly cost cap ${tracker.cap_usd:.2f} reached "
            f"(spent ${tracker.spent_usd:.4f})"
        )

    prompt = prompt_lib.load_and_render(prompt_name, **variables)
    messages = [{"role": "user", "content": prompt}]
    last_err: Exception | None = None

    # JSON/schema-validity retry loop: original attempt + 1 stricter-nudge retry.
    for json_attempt in range(2):
        text, usage, latency_ms = await _request_with_backoff(
            model=model, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        cost = tracker.record(model, usage[0], usage[1])
        _persist_cost(cost)
        log.info(
            "llm.call",
            prompt=prompt_name,
            model=model,
            schema=response_model.__name__,
            latency_ms=latency_ms,
            input_tokens=usage[0],
            output_tokens=usage[1],
            cost_usd=round(cost, 6),
            json_attempt=json_attempt,
        )
        try:
            return response_model.model_validate(_extract_json(text))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            log.warning(
                "llm.bad_output",
                prompt=prompt_name,
                model=model,
                json_attempt=json_attempt,
                error=str(e)[:200],
            )
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": _JSON_NUDGE},
            ]

    raise LLMError(
        f"{prompt_name}/{response_model.__name__}: invalid output after retry: {last_err}"
    )


async def _request_with_backoff(
    *, model: str, messages: list, max_tokens: int, temperature: float
) -> tuple[str, tuple[int, int], int]:
    """One logical request with rate-limit/5xx backoff. Returns
    (text, (input_tokens, output_tokens), latency_ms)."""
    from anthropic import APIConnectionError, APIStatusError, RateLimitError

    client = _client()
    last_err: Exception | None = None
    for attempt in range(len(_BACKOFF_SCHEDULE) + 1):
        t0 = time.monotonic()
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            )
            usage = (
                getattr(resp.usage, "input_tokens", 0),
                getattr(resp.usage, "output_tokens", 0),
            )
            return text, usage, round((time.monotonic() - t0) * 1000)
        except (RateLimitError, APIConnectionError) as e:
            last_err = e
            status = getattr(e, "status_code", 429)
        except APIStatusError as e:
            last_err = e
            status = getattr(e, "status_code", 500)
            if status not in _RETRYABLE_STATUS:
                raise
        if attempt < len(_BACKOFF_SCHEDULE):
            delay = _BACKOFF_SCHEDULE[attempt]
            log.warning("llm.backoff", model=model, attempt=attempt, delay_s=delay, status=status)
            await asyncio.sleep(delay)

    raise LLMError(f"LLM request failed after retries: {last_err}")
