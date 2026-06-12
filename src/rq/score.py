"""Scoring (§7.4).

Phase 1 lands the locally-computed, well-specified pieces — embeddings,
Laplace-smoothed domain reputation, novelty, recency decay — plus the weight
table. The LLM-driven component scoring and the final weighted combine are
wired up in Phase 3 (``rescore_item`` / ``rescore_all``).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .logging import get_logger

log = get_logger("score")

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384

# Component weights (sum = 100). See §7.4.
WEIGHTS = {
    "topic_match": 30,  # LLM
    "source_reputation": 20,  # computed
    "novelty": 15,  # computed
    "recency_value": 15,  # LLM
    "effort_payoff": 10,  # computed + LLM
    "surprise": 10,  # LLM
}


# --- embeddings (local, no API) ---------------------------------------------


@lru_cache(maxsize=1)
def _embedder():  # pragma: no cover - model load is heavy / network on first run
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL)


def embed_text(text: str) -> np.ndarray:
    """384-dim float32 embedding for novelty detection."""
    vec = _embedder().encode(text or "", normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)


def embedding_to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# --- computed components ----------------------------------------------------


def laplace_reputation(
    kept_or_read: int, killed: int, alpha: float = 3.0, prior: float = 0.5
) -> float:
    """Smoothed kept/(kept+killed) for a domain. Prior 0.5 with α=3 (§7.4)."""
    numerator = kept_or_read + alpha * prior
    denominator = kept_or_read + killed + alpha
    return numerator / denominator


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def novelty_score(embedding: np.ndarray, recent: list[np.ndarray]) -> float:
    """1 - max cosine similarity vs. recent embeddings (§7.4). 1.0 if none."""
    if not recent:
        return 1.0
    max_sim = max(cosine_similarity(embedding, e) for e in recent)
    return max(0.0, 1.0 - max_sim)


def recency_decay(days_old: float, news_y: bool, half_life_days: float = 7.0) -> float:
    """Multiplier in (0, 1]. Evergreen content doesn't decay; news-y content
    older than ~7 days loses value (§7.4)."""
    if not news_y or days_old <= half_life_days:
        return 1.0
    return float(0.5 ** ((days_old - half_life_days) / half_life_days))
