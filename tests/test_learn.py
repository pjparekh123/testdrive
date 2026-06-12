from __future__ import annotations

import itertools

from rq import db, learn
from rq.schemas import Item

_counter = itertools.count()


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
