from __future__ import annotations

import pytest

from rq import db, evaluate
from rq.evaluate import GoldenEntry, run_eval, spearman
from rq.schemas import Item


def test_spearman_monotonic():
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_handles_ties():
    # rank-based; constant series -> nan (no variance)
    import math

    assert math.isnan(spearman([1, 1, 1], [1, 2, 3]))


def _seed(conn, url, topic, pitch, tags):
    components = {
        "topic_match": {"score": topic, "reason": ""},
        "recency_value": {"score": 5, "reason": ""},
        "effort_payoff": {"score": 6, "reason": ""},
        "surprise": {"score": 5, "reason": ""},
    }
    item = Item(url=url, domain="d.com", pitch=pitch, tags=tags, score_breakdown=components)
    return db.insert_item(conn, item)


async def test_run_eval_reports_correlation_and_banned(conn):
    # Higher topic_match -> higher score; ratings track topic_match -> positive corr.
    _seed(conn, "https://d.com/a", topic=9, pitch="Maps every container ship lost at sea in 2023.", tags=["shipping"])
    _seed(conn, "https://d.com/b", topic=5, pitch="Argues upzoning lowered rents in three cities.", tags=["housing"])
    _seed(conn, "https://d.com/c", topic=1, pitch="This article is a must-read on crypto prices.", tags=["crypto"])
    conn.commit()

    golden = [
        GoldenEntry(url="https://d.com/a", my_rating=5, expected_tags=["shipping"]),
        GoldenEntry(url="https://d.com/b", my_rating=4, expected_tags=["housing"]),
        GoldenEntry(url="https://d.com/c", my_rating=1, expected_tags=["crypto"]),
    ]

    report = await run_eval(conn, golden, ingest_fn=None)

    assert report.scored == 3
    assert all(r.score is not None for r in report.rows)
    # Scores should increase with topic_match, matching the ratings order.
    assert report.correlation == pytest.approx(1.0)
    # The third pitch trips two banned phrases ("this article", "must-read").
    assert report.banned_count == 1
    banned_row = [r for r in report.rows if r.banned][0]
    assert "must-read" in banned_row.banned

    text = evaluate.format_report(report)
    assert "Spearman" in text and "BANNED" in text


async def test_run_eval_marks_missing_items(conn):
    golden = [GoldenEntry(url="https://nope.com/x", my_rating=3)]
    report = await run_eval(conn, golden, ingest_fn=None)
    assert report.rows[0].status == "not_ingested"
    assert report.scored == 0
