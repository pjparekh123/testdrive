from __future__ import annotations

import itertools

from rq import db, learn
from rq.config import Interests
from rq.schemas import Item

_counter = itertools.count()


def _resolve(conn, tags, kind, n):
    """Insert n items with the given tags, each resolved by event `kind`."""
    for _ in range(n):
        iid = db.insert_item(conn, Item(url=f"https://d.com/{next(_counter)}", domain="d.com", tags=tags))
        status = "killed" if kind == "killed" else "kept"
        conn.execute("UPDATE items SET status=? WHERE id=?", (status, iid))
        db.emit_event(conn, iid, kind, None)
    conn.commit()


def _add(conn, domain, status):
    item = Item(url=f"https://{domain}/{status}-{next(_counter)}", domain=domain, status=status)
    return db.insert_item(conn, item)


def test_update_domain_stats_computes_reputation(conn):
    for _ in range(3):
        _add(conn, "good.com", "kept")
    _add(conn, "good.com", "read")
    _add(conn, "good.com", "killed")
    conn.commit()

    rep = learn.update_domain_stats(conn, "good.com")

    row = conn.execute("SELECT * FROM domain_stats WHERE domain='good.com'").fetchone()
    assert row["total"] == 5
    assert row["kept_or_read"] == 4
    assert row["killed"] == 1
    # (4 + 3*0.5) / (4 + 1 + 3) = 5.5/8 = 0.6875
    assert rep == row["reputation"]
    assert abs(rep - 0.6875) < 1e-9


def test_update_domain_stats_is_upsert(conn):
    _add(conn, "x.com", "queued")
    learn.update_domain_stats(conn, "x.com")
    _add(conn, "x.com", "killed")
    learn.update_domain_stats(conn, "x.com")

    rows = conn.execute("SELECT COUNT(*) AS c FROM domain_stats WHERE domain='x.com'").fetchone()
    assert rows["c"] == 1  # updated in place, not duplicated


# --- interest drift (§7.6) --------------------------------------------------


def test_detect_interest_drift_suggests_add_and_remove(conn):
    # urban-planning: 8 kept / 2 killed, NOT in interests -> suggest ADD
    _resolve(conn, ["urban-planning"], "kept", 8)
    _resolve(conn, ["urban-planning"], "killed", 2)
    # systems-programming: 1 kept / 6 killed, IS in interests -> suggest REMOVE
    _resolve(conn, ["systems-programming"], "kept", 1)
    _resolve(conn, ["systems-programming"], "killed", 6)
    # below the sample threshold -> ignored
    _resolve(conn, ["niche"], "kept", 2)

    interests = Interests(active=["systems programming"])
    suggestions = learn.detect_interest_drift(conn, interests)

    by_tag = {s.tag: s for s in suggestions}
    assert by_tag["urban-planning"].action == "add"
    assert by_tag["urban-planning"].kept == 8 and by_tag["urban-planning"].total == 10
    assert by_tag["systems-programming"].action == "remove"
    assert "niche" not in by_tag

    text = by_tag["urban-planning"].to_text()
    assert "kept 8/10" in text and "urban-planning" in text


def test_detect_interest_drift_empty(conn):
    assert learn.detect_interest_drift(conn, Interests(active=["x"])) == []
