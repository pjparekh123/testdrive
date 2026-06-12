from __future__ import annotations

import itertools

from rq import db, learn
from rq.schemas import Item

_c = itertools.count()


def _add(conn, domain, status, score=None):
    iid = db.insert_item(conn, Item(url=f"https://{domain}/{next(_c)}", domain=domain,
                                    status=status, score=score))
    return iid


def test_avg_score_by_disposition(conn):
    _add(conn, "a.com", "kept", 80)
    _add(conn, "a.com", "read", 70)
    _add(conn, "b.com", "killed", 30)
    _add(conn, "b.com", "killed", 50)
    _add(conn, "c.com", "queued", 99)  # ignored (unresolved)
    kept, killed = db.avg_score_by_disposition(conn)
    assert kept == 75.0
    assert killed == 40.0


def test_top_domains_by_reputation(conn):
    for _ in range(5):
        _add(conn, "great.com", "kept")
    learn.update_domain_stats(conn, "great.com")
    for _ in range(4):
        _add(conn, "bad.com", "killed")
    learn.update_domain_stats(conn, "bad.com")
    _add(conn, "tiny.com", "kept")  # below min_total
    learn.update_domain_stats(conn, "tiny.com")
    conn.commit()

    top = db.top_domains_by_reputation(conn, n=5, min_total=2)
    domains = [d for d, *_ in top]
    assert domains[0] == "great.com"
    assert "bad.com" in domains
    assert "tiny.com" not in domains  # filtered by min_total


def test_top_domains_by_count(conn):
    for _ in range(3):
        _add(conn, "x.com", "queued")
    _add(conn, "y.com", "queued")
    top = db.top_domains_by_count(conn, 5)
    assert top[0] == ("x.com", 3)
