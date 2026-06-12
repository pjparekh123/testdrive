from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from rq import db, score
from rq.score import ComputedComponents
from rq.schemas import ScoreOutput


def test_laplace_reputation_prior_with_no_data():
    # No history -> prior 0.5 (α=3, prior=0.5).
    assert score.laplace_reputation(0, 0) == pytest.approx(0.5)


def test_laplace_reputation_smoothing():
    # 3 kept, 0 killed: (3 + 3*0.5) / (3 + 0 + 3) = 4.5/6 = 0.75
    assert score.laplace_reputation(3, 0) == pytest.approx(0.75)
    # Pulls toward prior, never reaches 1.0 on small samples.
    assert score.laplace_reputation(1, 0) < 1.0
    assert score.laplace_reputation(0, 10) < 0.2


def test_cosine_similarity():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0], dtype=np.float32)
    assert score.cosine_similarity(a, b) == pytest.approx(1.0)
    assert score.cosine_similarity(a, c) == pytest.approx(0.0)
    assert score.cosine_similarity(a, np.zeros(2, dtype=np.float32)) == 0.0


def test_novelty_score():
    v = np.array([1.0, 0.0], dtype=np.float32)
    assert score.novelty_score(v, []) == 1.0  # nothing to compare -> fully novel
    dup = [np.array([1.0, 0.0], dtype=np.float32)]
    assert score.novelty_score(v, dup) == pytest.approx(0.0)
    orth = [np.array([0.0, 1.0], dtype=np.float32)]
    assert score.novelty_score(v, orth) == pytest.approx(1.0)


def test_embedding_blob_roundtrip():
    v = np.arange(384, dtype=np.float32)
    blob = score.embedding_to_blob(v)
    back = score.blob_to_embedding(blob)
    assert back.shape == (384,)
    assert np.allclose(v, back)


# --- compute_recency_decay: linear to 0.3 over 14 days for news -------------


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def test_compute_recency_decay_evergreen():
    assert score.compute_recency_decay(_iso(100), is_news=False) == 1.0
    assert score.compute_recency_decay(None, is_news=False) == 1.0


def test_compute_recency_decay_news():
    assert score.compute_recency_decay(_iso(0), is_news=True) == 1.0
    assert score.compute_recency_decay(_iso(7), is_news=True) == pytest.approx(0.65, abs=0.02)
    assert score.compute_recency_decay(_iso(14), is_news=True) == pytest.approx(0.3, abs=0.02)
    assert score.compute_recency_decay(_iso(40), is_news=True) == 0.3
    # Undated news can't decay.
    assert score.compute_recency_decay(None, is_news=True) == 1.0


# --- compute_source_reputation (from domain_stats) --------------------------


def test_compute_source_reputation(conn):
    # No row -> prior 0.5.
    assert score.compute_source_reputation(conn, "unknown.com") == pytest.approx(0.5)
    conn.execute(
        "INSERT INTO domain_stats (domain, total, kept_or_read, killed, reputation) "
        "VALUES ('good.com', 9, 9, 0, 0)"
    )
    # 9 kept, 0 killed -> (9 + 1.5)/(9 + 3) = 0.875
    assert score.compute_source_reputation(conn, "good.com") == pytest.approx(0.875)


# --- compute_novelty (vs recent embeddings in DB) ---------------------------


def _add_item_with_embedding(conn, vec, domain="d.com", url=None):
    from rq.schemas import Item

    url = url or f"https://{domain}/{np.random.randint(1_000_000)}"
    return db.insert_item(
        conn, Item(url=url, domain=domain), embedding=score.embedding_to_blob(vec)
    )


def test_compute_novelty(conn):
    v = np.array([1.0, 0.0] + [0.0] * 382, dtype=np.float32)
    # Empty corpus -> fully novel.
    assert score.compute_novelty(conn, v) == 1.0
    # Insert a near-duplicate -> low novelty.
    _add_item_with_embedding(conn, v)
    assert score.compute_novelty(conn, v) == pytest.approx(0.0, abs=1e-5)
    # Orthogonal item is still highly novel relative to itself excluded.
    orth = np.array([0.0, 1.0] + [0.0] * 382, dtype=np.float32)
    assert score.compute_novelty(conn, orth) == pytest.approx(1.0, abs=1e-5)


# --- compute_final_score (weighted sum) -------------------------------------


def _components(t, r, e, s) -> ScoreOutput:
    return ScoreOutput.model_validate(
        {
            "topic_match": {"score": t, "reason": ""},
            "recency_value": {"score": r, "reason": ""},
            "effort_payoff": {"score": e, "reason": ""},
            "surprise": {"score": s, "reason": ""},
        }
    )


def test_compute_final_score_max():
    comp = _components(10, 10, 10, 10)
    computed = ComputedComponents(source_reputation=1.0, novelty=1.0, recency_decay=1.0, is_news=False)
    assert score.compute_final_score(comp, computed) == 100


def test_compute_final_score_midpoint():
    comp = _components(5, 5, 5, 5)
    computed = ComputedComponents(0.5, 0.5, 1.0, False)
    # 30*.5 + 20*.5 + 15*.5 + 15*.5*1 + 10*.5 + 10*.5 = 50
    assert score.compute_final_score(comp, computed) == 50


def test_compute_final_score_recency_decay_applies():
    comp = _components(5, 10, 5, 5)
    full = ComputedComponents(0.5, 0.5, 1.0, True)
    decayed = ComputedComponents(0.5, 0.5, 0.3, True)
    assert score.compute_final_score(comp, full) > score.compute_final_score(comp, decayed)
