"""Pydantic schemas — the contract between modules.

No ``dict[str, Any]`` ever crosses a module boundary. Every LLM call returns
one of the ``*Output`` models below via ``response_model=...`` in the wrapper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["queued", "read", "killed", "kept", "archived"]
AddedVia = Literal["telegram", "cli", "shortcut", "import"]


# --- Extraction -------------------------------------------------------------


class ExtractedPage(BaseModel):
    """Output of fetch.fetch_and_extract (§9)."""

    title: str
    author: str | None = None
    published_at: str | None = None
    text: str
    word_count: int
    paywalled: bool = False


# --- LLM outputs ------------------------------------------------------------


class SummarizeOutput(BaseModel):
    tldr: str = Field(max_length=300)
    summary: str = Field(max_length=2000)
    tags: list[str] = Field(min_length=1, max_length=6)


class PitchOutput(BaseModel):
    pitch: str = Field(max_length=150)


class ComponentScore(BaseModel):
    score: int = Field(ge=0, le=10)
    reason: str = Field(max_length=200)


class ScoreOutput(BaseModel):
    topic_match: ComponentScore
    recency_value: ComponentScore
    effort_payoff: ComponentScore
    surprise: ComponentScore


# --- Domain model -----------------------------------------------------------


class Item(BaseModel):
    """In-memory representation of a row in the ``items`` table.

    ``add_url`` and the CLI/bot pass this around rather than raw dicts.
    """

    id: int | None = None
    url: str
    canonical_url: str | None = None
    domain: str
    title: str | None = None
    author: str | None = None
    published_at: str | None = None
    added_at: datetime | None = None
    fetched_at: datetime | None = None
    raw_text: str | None = None
    word_count: int | None = None
    read_minutes: float | None = None
    summary: str | None = None
    tldr: str | None = None
    pitch: str | None = None
    tags: list[str] = Field(default_factory=list)
    score: int | None = None
    score_breakdown: dict | None = None
    status: Status = "queued"
    added_via: AddedVia | None = None
    last_surfaced_at: datetime | None = None
    surface_count: int = 0
