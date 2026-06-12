"""llm.py wrapper tests — retry logic + Pydantic validation, via VCR cassettes.

No live API: vcrpy intercepts the Anthropic SDK's httpx calls and replays the
hand-authored cassettes in tests/cassettes/.
"""

from __future__ import annotations

import pytest

from rq import llm
from rq.schemas import SummarizeOutput

pytestmark = pytest.mark.usefixtures("anthropic_env")


async def test_call_parses_and_validates(my_vcr):
    with my_vcr.use_cassette("summarize_ok.yaml"):
        out = await llm.call(
            "summarize",
            {"title": "Container ships", "text": "..."},
            SummarizeOutput,
            "claude-haiku-4-5-20251001",
        )
    assert isinstance(out, SummarizeOutput)
    assert out.tags and len(out.tags) <= 6
    assert out.tldr.startswith("Container ships")


async def test_call_retries_on_invalid_output_then_succeeds(my_vcr):
    # First response violates the schema (empty tags); wrapper appends the nudge
    # and the second response validates.
    with my_vcr.use_cassette("summarize_validation_retry.yaml"):
        out = await llm.call(
            "summarize", {"title": "t", "text": "x"}, SummarizeOutput,
            "claude-haiku-4-5-20251001",
        )
    assert isinstance(out, SummarizeOutput)
    assert out.tags == ["shipping", "logistics", "infrastructure", "autonomous-vessels"]


async def test_call_hard_fails_after_retry(my_vcr):
    # Two non-JSON responses -> LLMError (original attempt + one nudge retry).
    with my_vcr.use_cassette("summarize_badjson_twice.yaml"):
        with pytest.raises(llm.LLMError):
            await llm.call(
                "summarize", {"title": "t", "text": "x"}, SummarizeOutput,
                "claude-haiku-4-5-20251001",
            )


async def test_call_backs_off_on_rate_limit(my_vcr, no_sleep):
    # 429 then 200: wrapper backs off (sleep patched to instant) and recovers.
    with my_vcr.use_cassette("ratelimit_then_ok.yaml"):
        out = await llm.call(
            "summarize", {"title": "t", "text": "x"}, SummarizeOutput,
            "claude-haiku-4-5-20251001",
        )
    assert isinstance(out, SummarizeOutput)


async def test_cost_cap_blocks_calls(my_vcr, monkeypatch):
    # Pre-spend past the cap; the next call is refused before any HTTP request.
    tracker = llm._cost_tracker()
    tracker.spent_usd = tracker.cap_usd + 1
    with pytest.raises(llm.CostCapExceeded):
        await llm.call(
            "summarize", {"title": "t", "text": "x"}, SummarizeOutput,
            "claude-haiku-4-5-20251001",
        )
