"""Digest composer + selection + surfacing tests, plus a snapshot of the
20-item message.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rq import db
from rq.config import get_settings
from rq.digest import DigestStats, compose_message, select_items, send_digest
from rq.schemas import Item

_ids = itertools.count(1)

SNAPSHOT = Path(__file__).parent / "snapshots" / "digest_message.md"
NOW = datetime(2026, 6, 14, 9, 0, tzinfo=timezone.utc)  # a Sunday 9am


def _it(i, **kw):
    return Item(
        id=i,
        url=f"https://{kw.get('domain', 'x.com')}/{i}",
        domain=kw.get("domain", "x.com"),
        title=kw.get("title"),
        pitch=kw.get("pitch"),
        read_minutes=kw.get("rm"),
        score=kw.get("score"),
        added_at=kw.get("added"),
    )


def _fixture_20():
    read_this = [
        _it(1, pitch="A neuroscientist argues your morning anxiety starts in your liver, not your brain.", rm=12, score=91, domain="nautil.us"),
        _it(2, pitch="Maps every container ship lost at sea in 2023; the pattern surprised me.", rm=7, score=84, domain="lloydslist.com"),
        _it(3, pitch="Why TypeScript's `satisfies` operator quietly replaced half your type assertions.", rm=5, score=78, domain="2ality.com"),
    ]
    skim = [
        _it(4, title="The case for single-stair apartment buildings", rm=9, score=66, domain="worksinprogress.co"),
        _it(5, title="A field guide to async Rust cancellation", rm=14, score=61, domain="without.boats"),
        _it(6, title="What 50 years of attention research actually shows", rm=18, score=58, domain="theatlantic.com"),
        _it(7, title="Tokyo's quiet zoning revolution", rm=6, score=54, domain="ft.com"),
        _it(8, title="Benchmarking LLM agents: a skeptic's checklist", rm=11, score=52, domain="arxiv.org"),
    ]
    kill = [
        _it(9, title="10 VS Code extensions you must install", domain="medium.com", added=NOW - timedelta(days=22)),
        _it(10, title="The ultimate guide to morning routines", domain="dev.to", added=NOW - timedelta(days=31)),
        _it(11, title="Why this altcoin could 50x in 2024", domain="cryptodaily.io", added=NOW - timedelta(days=19)),
        _it(12, title="Thread: my hot takes on the VC meltdown", domain="x.com", added=NOW - timedelta(days=16)),
    ]
    # (3 + 5 + 4 = 12 surfaced; the other 8 of the 20 are below the bar / fresh.)
    return read_this, skim, kill


def test_compose_matches_snapshot():
    read_this, skim, kill = _fixture_20()
    msg = compose_message(read_this, skim, kill, DigestStats(queue_size=47, goal=30), now=NOW)
    if not SNAPSHOT.exists():  # first run writes the snapshot
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(msg)
    assert msg == SNAPSHOT.read_text(), "digest output changed — review and update the snapshot"


def test_compose_escapes_markdown_v2():
    msg = compose_message(
        [_it(1, pitch="It dropped a lot (a lot). See www.x.com!", rm=3, score=80, domain="x.com")],
        [], [], DigestStats(1, 30), now=NOW,
    )
    # the dynamic content's MarkdownV2 specials are escaped
    assert "\\(a lot\\)" in msg and "\\!" in msg and "www\\.x\\.com" in msg


def test_compose_empty_queue():
    msg = compose_message([], [], [], DigestStats(0, 30), now=NOW)
    assert "Your queue is clear" in msg


# --- selection rules --------------------------------------------------------


def _add(conn, *, score, status="queued", added_days=1, surfaced=0, last_surfaced=None, opened=False):
    item = Item(url=f"https://d.com/{next(_ids)}", domain="d.com",
                title=f"item {score}", score=score, status=status, surface_count=surfaced)
    iid = db.insert_item(conn, item)
    conn.execute(
        "UPDATE items SET added_at=datetime('now', ?), last_surfaced_at=? WHERE id=?",
        (f"-{added_days} days", last_surfaced, iid),
    )
    if opened:
        db.emit_event(conn, iid, "opened", None)
    conn.commit()
    return iid


def test_select_read_this_respects_score_and_surface_window(conn):
    _add(conn, score=90)  # qualifies
    _add(conn, score=72)  # qualifies
    _add(conn, score=65)  # too low for read_this (goes to skim)
    _add(conn, score=95, last_surfaced="2099-01-01 00:00:00")  # surfaced "recently" -> excluded

    sel = select_items(conn)
    scores = sorted(i.score for i in sel.read_this)
    assert scores == [72, 90]  # 95 excluded (recently surfaced), 65 not in band


def test_select_skim_band(conn):
    _add(conn, score=69)
    _add(conn, score=50)
    _add(conn, score=49)  # below band
    _add(conn, score=70)  # above band (read_this)
    sel = select_items(conn)
    assert sorted(i.score for i in sel.skim) == [50, 69]


def test_select_kill_candidates(conn):
    _add(conn, score=40, added_days=20, surfaced=2)  # stale + surfaced -> candidate
    _add(conn, score=40, added_days=20, surfaced=0)  # never surfaced -> not yet
    _add(conn, score=40, added_days=2, surfaced=5)   # too fresh
    _add(conn, score=40, added_days=20, surfaced=3, opened=True)  # opened -> excluded
    sel = select_items(conn)
    assert len(sel.kill_these) == 1


# --- surfacing side effects -------------------------------------------------


async def test_send_digest_dry_run_does_not_mutate(conn):
    _add(conn, score=90)
    text = await send_digest(conn=conn, dry_run=True, now=NOW)
    assert "Weekly Reading Queue" in text
    row = conn.execute("SELECT surface_count, last_surfaced_at FROM items").fetchone()
    assert row["surface_count"] == 0 and row["last_surfaced_at"] is None


async def test_send_digest_marks_surfaced(conn, monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    get_settings.cache_clear()
    iid = _add(conn, score=90)
    bot = AsyncMock()
    await send_digest(conn=conn, bot=bot, dry_run=False, now=NOW)

    bot.send_message.assert_awaited()  # would have sent
    row = conn.execute("SELECT surface_count, last_surfaced_at FROM items WHERE id=?", (iid,)).fetchone()
    assert row["surface_count"] == 1 and row["last_surfaced_at"] is not None
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (iid,))]
    assert "surfaced" in kinds
    get_settings.cache_clear()  # don't leak the allowed-users env to other tests
