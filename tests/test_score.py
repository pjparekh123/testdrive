from __future__ import annotations

import numpy as np
import pytest

from rq import score


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


def test_recency_decay():
    assert score.recency_decay(0, news_y=True) == 1.0
    assert score.recency_decay(100, news_y=False) == 1.0  # evergreen never decays
    assert score.recency_decay(7, news_y=True) == 1.0  # within half-life window
    assert score.recency_decay(14, news_y=True) == pytest.approx(0.5)


def test_embedding_blob_roundtrip():
    v = np.arange(384, dtype=np.float32)
    blob = score.embedding_to_blob(v)
    back = score.blob_to_embedding(blob)
    assert back.shape == (384,)
    assert np.allclose(v, back)
