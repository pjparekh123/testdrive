from __future__ import annotations

import numpy as np
import pytest

from rq import ingest
from rq.enrich import EnrichmentResult
from rq.fetch import canonicalize_url, domain_of
from rq.schemas import ExtractedPage, ScoreOutput


# --- URL normalization (pure) ----------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # utm params stripped, real query kept
        ("https://a.com/p?utm_source=twitter&id=5", "https://a.com/p?id=5"),
        ("https://a.com/p?utm_medium=x&utm_campaign=y", "https://a.com/p"),
        # fbclid / gclid stripped
        ("https://a.com/p?fbclid=abc", "https://a.com/p"),
        ("https://a.com/p?gclid=xyz&q=1", "https://a.com/p?q=1"),
        # trailing slash removed (but bare-root slash preserved)
        ("https://a.com/path/", "https://a.com/path"),
        ("https://a.com/", "https://a.com/"),
        # fragment identifiers dropped
        ("https://a.com/p#section-2", "https://a.com/p"),
        ("https://a.com/p?id=5#frag", "https://a.com/p?id=5"),
        ("https://a.com/path/#top", "https://a.com/path"),
        # already-canonical URLs are unchanged (idempotent)
        ("https://a.com/p?id=5", "https://a.com/p?id=5"),
        ("https://a.com/clean-path", "https://a.com/clean-path"),
        # combined: utm + fbclid + trailing slash + fragment
        ("https://a.com/p/?utm_source=x&fbclid=y&q=1#go", "https://a.com/p?q=1"),
    ],
)
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


def test_canonicalize_is_idempotent():
    once = canonicalize_url("https://a.com/p/?utm_source=x#frag")
    assert canonicalize_url(once) == once


def test_domain_of_strips_www():
    assert domain_of("https://www.Example.com/x") == "example.com"
    assert domain_of("https://news.ycombinator.com/item?id=1") == "news.ycombinator.com"


# --- add_url end-to-end (faked fetch, real DB) ------------------------------


def _fake_page(words: int = 300):
    async def _fetch(url: str) -> ExtractedPage:
        return ExtractedPage(
            title="Container ships lost at sea",
            author="J. Doe",
            text=" ".join(["word"] * words),
            word_count=words,
        )

    return _fetch


def _fake_enrichment():
    components = ScoreOutput.model_validate(
        {
            "topic_match": {"score": 7, "reason": "matches"},
            "recency_value": {"score": 4, "reason": "evergreen"},
            "effort_payoff": {"score": 8, "reason": "short"},
            "surprise": {"score": 5, "reason": "mild"},
        }
    )

    async def _enrich(page, interests, recent_kept_titles):
        return EnrichmentResult(
            summary="A dense, concrete summary.",
            tldr="One neutral sentence.",
            tags=["shipping", "logistics"],
            pitch="Maps every container ship lost at sea in 2023; the pattern surprised me.",
            score_components=components,
            embedding=np.ones(384, dtype=np.float32),
        )

    return _enrich


async def test_add_url_stores_enriched_row(conn, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_and_extract", _fake_page(300))
    monkeypatch.setattr(ingest, "enrich", _fake_enrichment())

    item = await ingest.add_url(
        "https://blog.example.com/ships?utm_source=x", source="cli", conn=conn
    )

    assert item.id is not None
    assert item.raw_text and item.word_count == 300
    assert item.read_minutes == pytest.approx(300 / 230, abs=0.01)
    assert item.canonical_url == "https://blog.example.com/ships"
    assert item.status == "queued"

    # Real enrichment fields populated; final score deferred to Phase 3.
    assert item.summary == "A dense, concrete summary."
    assert item.tldr == "One neutral sentence."
    assert item.tags == ["shipping", "logistics"]
    assert item.pitch.startswith("Maps every container ship")
    assert item.score is None
    assert item.score_breakdown["topic_match"]["score"] == 7

    # Embedding persisted as a 384-d float32 blob.
    row = conn.execute(
        "SELECT embedding, score, score_breakdown_json FROM items WHERE id=?", (item.id,)
    ).fetchone()
    assert row["embedding"] is not None and len(row["embedding"]) == 384 * 4
    assert row["score"] is None and row["score_breakdown_json"]

    # Phase 2 emits `added` + `enriched`.
    kinds = [
        r["kind"]
        for r in conn.execute("SELECT kind FROM events WHERE item_id=? ORDER BY id", (item.id,))
    ]
    assert kinds == ["added", "enriched"]


async def test_add_url_dedupes_without_resetting_surface_count(conn, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_and_extract", _fake_page(300))
    monkeypatch.setattr(ingest, "enrich", _fake_enrichment())

    first = await ingest.add_url("https://a.com/p", conn=conn)
    # Simulate the item having been surfaced twice already.
    conn.execute("UPDATE items SET surface_count=2 WHERE id=?", (first.id,))
    conn.commit()

    second = await ingest.add_url("https://a.com/p?utm_source=feed", conn=conn)

    assert second.id == first.id
    row = conn.execute(
        "SELECT surface_count FROM items WHERE id=?", (first.id,)
    ).fetchone()
    assert row["surface_count"] == 2  # left alone, not reset to 0

    count = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
    assert count == 1


async def test_add_url_fetch_failure_still_stores_queued(conn, monkeypatch):
    async def _empty(url: str) -> ExtractedPage:
        return ExtractedPage(title=url, text="", word_count=0)

    monkeypatch.setattr(ingest, "fetch_and_extract", _empty)

    item = await ingest.add_url("https://broken.example.com/x", conn=conn)
    assert item.status == "queued"
    assert item.raw_text is None
    assert item.fetched_at is None
    kinds = [
        r["kind"]
        for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (item.id,))
    ]
    assert kinds == ["added"]
