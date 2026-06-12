from __future__ import annotations

from pathlib import Path

import pytest
import vcr

from rq import db, llm
from rq.config import get_settings

CASSETTES = Path(__file__).parent / "cassettes"


@pytest.fixture
def conn(tmp_path: Path):
    """A migrated SQLite connection backed by a throwaway file."""
    settings = get_settings()
    c = db.connect(tmp_path / "test.db")
    db.migrate(c, settings.migrations_dir)
    yield c
    c.close()


@pytest.fixture
def anthropic_env(monkeypatch):
    """Give the SDK a dummy key and reset the wrapper's cached client/tracker so
    each test starts clean (no real network — VCR intercepts httpx)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()
    llm._client.cache_clear()
    llm._cost_tracker.cache_clear()
    yield
    get_settings.cache_clear()
    llm._client.cache_clear()
    llm._cost_tracker.cache_clear()


@pytest.fixture
def no_sleep(monkeypatch):
    """Make backoff instant so rate-limit tests don't actually wait."""
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _instant)


def _prompt_kind(body) -> str:
    if body is None:
        return "other"
    if isinstance(body, bytes):
        body = body.decode("utf-8", "ignore")
    if "summarizing an article" in body:
        return "summarize"
    if "one-line pitches" in body:
        return "pitch"
    if "scoring an article" in body:
        return "score"
    return "other"


def _match_prompt_kind(r1, r2) -> bool:
    return _prompt_kind(r1.body) == _prompt_kind(r2.body)


def make_vcr() -> vcr.VCR:
    v = vcr.VCR(
        cassette_library_dir=str(CASSETTES),
        record_mode="none",  # replay only; never hit the network in CI
        match_on=["method", "scheme", "host", "port", "path"],
    )
    v.register_matcher("prompt_kind", _match_prompt_kind)
    return v


@pytest.fixture
def my_vcr() -> vcr.VCR:
    return make_vcr()
