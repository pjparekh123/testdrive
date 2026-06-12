from __future__ import annotations

import pytest

from rq import ingest
from rq.fetch import canonicalize_url, domain_of
from rq.schemas import ExtractedPage


# --- URL normalization (pure) ----------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://a.com/p?utm_source=twitter&id=5", "https://a.com/p?id=5"),
        ("https://a.com/p?fbclid=abc", "https://a.com/p"),
        ("https://a.com/p?gclid=xyz&q=1", "https://a.com/p?q=1"),
        ("https://a.com/path/", "https://a.com/path"),
        ("https://a.com/", "https://a.com/"),
        ("https://a.com/p?utm_medium=x&utm_campaign=y", "https://a.com/p"),
    ],
)
def test_canonicalize_url(raw, expected):
    assert canonicalize_url(raw) == expected


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


async def test_add_url_stores_row_with_raw_text(conn, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_and_extract", _fake_page(300))

    item = await ingest.add_url(
        "https://blog.example.com/ships?utm_source=x", source="cli", conn=conn
    )

    assert item.id is not None
    assert item.raw_text and item.word_count == 300
    assert item.read_minutes == pytest.approx(300 / 230, abs=0.01)
    assert item.canonical_url == "https://blog.example.com/ships"
    assert item.domain == "blog.example.com"
    assert item.status == "queued"

    kinds = {
        r["kind"]
        for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (item.id,))
    }
    assert {"added", "fetched", "enriched"} <= kinds


async def test_add_url_dedupes_without_resetting_surface_count(conn, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_and_extract", _fake_page(300))

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
        return ExtractedPage(title=url, text="", word_count=0, needs_review=True)

    monkeypatch.setattr(ingest, "fetch_and_extract", _empty)

    item = await ingest.add_url("https://broken.example.com/x", conn=conn)
    assert item.status == "queued"
    assert item.raw_text is None
    kinds = {
        r["kind"]
        for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (item.id,))
    }
    assert "error" in kinds
