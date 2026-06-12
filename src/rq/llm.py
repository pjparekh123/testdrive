"""The one LLM wrapper. Every LLM call in the codebase goes through here.

Responsibilities (§5 hard requirement):
  * retries — JSON-parse failure (1 stricter-nudge retry) and rate-limit/5xx
    backoff (2s, 8s, 30s; max 3 tries)
  * JSON parsing + Pydantic validation against a ``response_model``
  * structured logging (model, latency, tokens, cost, attempt)
  * cost tracking with a hard monthly cap (§18)

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

from .config import Settings, get_settings
from .logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)

# Approximate prices in USD per 1M tokens (input, output). Configurable; used
# only for the cost ledger / monthly cap — not billed against.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}
_BACKOFF_SCHEDULE = (2.0, 8.0, 30.0)
_JSON_NUDGE = (
    "Your previous output was not valid JSON. Return only the JSON object, "
    "with no prose and no markdown fences."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(RuntimeError):
    """Raised when the wrapper cannot return a validated response."""


class CostCapExceeded(LLMError):
    """Raised when an enrichment would push spend over the monthly cap."""


class CostTracker:
    """In-process running tally of LLM spend for the current month.

    A personal-scale ledger: the digest/enrichment paths consult ``would_exceed``
    before spending and ``record`` after. Persisted spend can be layered on later
    (Day 6); for now this guards a single long-running process.
    """

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
def _cost_tracker() -> CostTracker:
    return CostTracker(get_settings().monthly_cost_cap_usd)


@lru_cache(maxsize=1)
def _client():  # pragma: no cover - thin SDK construction
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of model text, tolerating markdown fences."""
    candidate = text.strip()
    m = _FENCE_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]
    return json.loads(candidate)


async def complete(
    *,
    prompt: str,
    response_model: type[T],
    model: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    settings: Settings | None = None,
) -> T:
    """Run one LLM call and return a validated ``response_model`` instance.

    Raises ``LLMError`` if the model never returns valid, schema-conforming JSON,
    or ``CostCapExceeded`` if the monthly cap is already hit.
    """
    s = settings or get_settings()
    tracker = _cost_tracker()
    if tracker.would_exceed():
        raise CostCapExceeded(
            f"monthly cost cap ${tracker.cap_usd:.2f} reached "
            f"(spent ${tracker.spent_usd:.4f}); enrichment queued"
        )

    client = _client()
    messages = [{"role": "user", "content": prompt}]
    last_err: Exception | None = None

    # JSON-validity retry loop (max 2 attempts: original + 1 stricter nudge).
    for json_attempt in range(2):
        text, usage = await _call_with_backoff(
            client, model=model, messages=messages, max_tokens=max_tokens,
            temperature=temperature,
        )
        cost = tracker.record(model, usage[0], usage[1])
        try:
            data = _extract_json(text)
            obj = response_model.model_validate(data)
            log.info(
                "llm.ok",
                model=model,
                schema=response_model.__name__,
                in_tokens=usage[0],
                out_tokens=usage[1],
                cost_usd=round(cost, 6),
                json_attempt=json_attempt,
            )
            return obj
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            log.warning(
                "llm.bad_json",
                model=model,
                schema=response_model.__name__,
                json_attempt=json_attempt,
                error=str(e)[:200],
            )
            # Feed the model its own output + a stricter nudge, then retry once.
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": _JSON_NUDGE},
            ]

    raise LLMError(
        f"{response_model.__name__}: model did not return valid JSON after retry: "
        f"{last_err}"
    )


async def _call_with_backoff(
    client, *, model: str, messages: list, max_tokens: int, temperature: float
) -> tuple[str, tuple[int, int]]:
    """Single logical request with rate-limit/5xx backoff. Returns (text,
    (in_tokens, out_tokens))."""
    from anthropic import APIStatusError, APIConnectionError, RateLimitError

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
                block.text for block in resp.content if getattr(block, "type", None) == "text"
            )
            usage = (
                getattr(resp.usage, "input_tokens", 0),
                getattr(resp.usage, "output_tokens", 0),
            )
            log.info("llm.call", model=model, latency_ms=round((time.monotonic() - t0) * 1000))
            return text, usage
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
