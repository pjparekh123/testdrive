from __future__ import annotations

from rq import db, ingest
from rq.llm import CostCapExceeded
from rq.schemas import ExtractedPage


async def _page(url):
    return ExtractedPage(title="T", author=None, text=" ".join(["w"] * 300), word_count=300)


async def test_cost_cap_saves_raw_text_only(conn, monkeypatch):
    monkeypatch.setattr(ingest, "fetch_and_extract", _page)

    async def capped(*a, **k):
        raise CostCapExceeded("monthly cap reached")

    monkeypatch.setattr(ingest, "enrich", capped)

    item = await ingest.add_url("https://blog.example.com/x", conn=conn)

    # raw_text saved, queued, but unenriched
    assert item.status == "queued"
    assert item.raw_text and item.word_count == 300
    assert item.summary is None and item.pitch is None and item.score is None

    # the 'added' event records the cost-cap deferral; no 'enriched' event
    rows = list(conn.execute("SELECT kind, payload_json FROM events WHERE item_id=?", (item.id,)))
    kinds = [r["kind"] for r in rows]
    assert kinds == ["added"]
    assert '"cost_capped": true' in rows[0]["payload_json"]


def test_month_spend_ledger(conn):
    assert db.get_month_spend(conn) == 0.0
    db.add_month_spend(conn, 0.0012)
    db.add_month_spend(conn, 0.0008)
    assert db.get_month_spend(conn) == 0.002
    # isolated per month
    assert db.get_month_spend(conn, "1999-01") == 0.0
