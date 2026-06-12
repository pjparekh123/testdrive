from __future__ import annotations

import pytest
from pydantic import ValidationError

from rq.schemas import (
    ComponentScore,
    ExtractedPage,
    Item,
    PitchOutput,
    ScoreOutput,
    SummarizeOutput,
)


def test_extracted_page_defaults():
    p = ExtractedPage(title="T", text="hello world", word_count=2)
    assert p.author is None
    assert p.paywalled is False
    assert p.needs_review is False


def test_summarize_output_tag_bounds():
    SummarizeOutput(tldr="x", summary="y", tags=["a"])
    with pytest.raises(ValidationError):
        SummarizeOutput(tldr="x", summary="y", tags=[])  # min_length=1
    with pytest.raises(ValidationError):
        SummarizeOutput(tldr="x", summary="y", tags=list("abcdefg"))  # max_length=6


def test_pitch_output_length_cap():
    PitchOutput(pitch="a short pitch")
    with pytest.raises(ValidationError):
        PitchOutput(pitch="x" * 151)


def test_component_score_range():
    ComponentScore(score=0, reason="ok")
    ComponentScore(score=10, reason="ok")
    with pytest.raises(ValidationError):
        ComponentScore(score=11, reason="too high")
    with pytest.raises(ValidationError):
        ComponentScore(score=-1, reason="too low")


def test_score_output_requires_all_components():
    cs = {"score": 5, "reason": "meh"}
    ScoreOutput(topic_match=cs, recency_value=cs, effort_payoff=cs, surprise=cs)
    with pytest.raises(ValidationError):
        ScoreOutput(topic_match=cs, recency_value=cs, effort_payoff=cs)


def test_item_tags_default_empty():
    it = Item(url="https://x.com/a", domain="x.com")
    assert it.tags == []
    assert it.status == "queued"
    assert it.surface_count == 0
