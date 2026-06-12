"""Enrichment pipeline tests.

`enrich()` runs three real Anthropic calls (summarize -> pitch + score) through
the llm wrapper; here they're replayed from one cassette matched by prompt kind
(so the concurrent pitch/score calls resolve regardless of order). The embedding
is stubbed because HuggingFace isn't reachable in CI.
"""

from __future__ import annotations

import numpy as np
import pytest

from rq import enrich as enrich_mod
from rq.config import Interests
from rq.enrich import EnrichmentResult, enrich
from rq.schemas import ExtractedPage, ScoreOutput

pytestmark = pytest.mark.usefixtures("anthropic_env")

BANNED = ["this article", "the author argues", "in this piece", "game-changing",
          "must-read", "fascinating"]


def pitch_is_good(pitch: str) -> tuple[bool, str]:
    words = pitch.split()
    if len(words) > 15:
        return False, f"{len(words)} words (>15)"
    low = pitch.lower()
    for phrase in BANNED:
        if phrase in low:
            return False, f"banned phrase: {phrase!r}"
    return True, "ok"


@pytest.fixture
def page():
    return ExtractedPage(
        title="The Quiet Comeback of the Container Ship",
        author="Jane Mariner",
        published_at="2026-05-01",
        text="Container shipping " * 60,
        word_count=223,
    )


@pytest.fixture
def interests():
    return Interests(active=["systems programming", "infrastructure"], avoid=["crypto"])


async def test_enrich_runs_three_passes(my_vcr, page, interests, monkeypatch):
    monkeypatch.setattr(
        enrich_mod.score, "embed_text", lambda t: np.ones(384, dtype=np.float32)
    )
    with my_vcr.use_cassette("enrich_full.yaml", match_on=["prompt_kind"]):
        result = await enrich(page, interests, recent_kept_titles=[])

    assert isinstance(result, EnrichmentResult)
    assert isinstance(result.score_components, ScoreOutput)
    assert result.tags == ["shipping", "logistics", "infrastructure", "autonomous-vessels"]
    assert result.summary.startswith("Container ships have grown")
    assert result.score_components.topic_match.score == 6
    assert result.embedding is not None and result.embedding.shape == (384,)


async def test_enrich_pitch_quality(my_vcr, page, interests, monkeypatch):
    monkeypatch.setattr(enrich_mod.score, "embed_text", lambda t: np.ones(384, dtype=np.float32))
    with my_vcr.use_cassette("enrich_full.yaml", match_on=["prompt_kind"]):
        result = await enrich(page, interests, recent_kept_titles=[])

    good, why = pitch_is_good(result.pitch)
    assert good, f"pitch failed quality check ({why}): {result.pitch!r}"


async def test_enrich_embedding_best_effort_when_model_unavailable(
    my_vcr, page, interests, monkeypatch
):
    def boom(_text):
        raise RuntimeError("offline: cannot download model")

    monkeypatch.setattr(enrich_mod.score, "embed_text", boom)
    with my_vcr.use_cassette("enrich_full.yaml", match_on=["prompt_kind"]):
        result = await enrich(page, interests, recent_kept_titles=[])

    assert result.embedding is None  # non-fatal: enrichment still returns
    assert result.pitch  # other fields populated
