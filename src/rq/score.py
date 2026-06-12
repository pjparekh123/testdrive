"""Scoring (§7.4).

The locally-computed components (embeddings, Laplace-smoothed domain reputation,
novelty, recency decay), the LLM-component combine, and the rescore orchestration
all live here. Final score is a weighted sum, 0–100.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np

from . import db
from .logging import get_logger
from .schemas import Item, ScoreOutput

log = get_logger("score")

# Pitch hygiene — banned phrases/marketing words (§8.2), reused by the eval.
BANNED_PHRASES = [
    "this article",
    "the author argues",
    "in this piece",
    "game-changing",
    "must-read",
    "fascinating",
]


@dataclass
class ComputedComponents:
    """The Python-computed half of the score (the LLM half is ``ScoreOutput``)."""

    source_reputation: float  # 0–1
    novelty: float  # 0–1
    recency_decay: float  # 0–1 multiplier on the recency component
    is_news: bool

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


def _days_since(published_at: str | None) -> int | None:
    if not published_at:
        return None
    raw = published_at.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[: len(datetime.now().strftime(fmt)) + 6], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except ValueError:
            continue
    return None


# --- the prescribed compute_* API (§7.4) ------------------------------------


def compute_source_reputation(conn: sqlite3.Connection, domain: str) -> float:
    """Laplace-smoothed kept/(kept+killed) for ``domain`` from domain_stats."""
    row = conn.execute(
        "SELECT kept_or_read, killed FROM domain_stats WHERE domain=?", (domain,)
    ).fetchone()
    kept = row["kept_or_read"] if row else 0
    killed = row["killed"] if row else 0
    return laplace_reputation(kept, killed)


def compute_novelty(
    conn: sqlite3.Connection, embedding: np.ndarray, exclude_id: int | None = None
) -> float:
    """1 - max cosine similarity vs. the last 50 items' embeddings."""
    recent = [blob_to_embedding(b) for b in db.recent_embeddings(conn, 50, exclude_id)]
    return novelty_score(embedding, recent)


def compute_recency_decay(published_at: str | None, is_news: bool) -> float:
    """1.0 for evergreen; for news, decays linearly to 0.3 over 14 days.

    Undated or future-dated content does not decay (returns 1.0).
    """
    if not is_news:
        return 1.0
    days = _days_since(published_at)
    if days is None or days <= 0:
        return 1.0
    if days >= 14:
        return 0.3
    return 1.0 - 0.7 * (days / 14)


def compute_final_score(
    components: ScoreOutput, computed: ComputedComponents
) -> int:
    """Weighted sum over the §7.4 table, returns a 0–100 int.

    LLM components are 0–10 (normalized to 0–1); computed components are already
    0–1. The recency component is the LLM recency value scaled by the decay.
    """
    total = (
        WEIGHTS["topic_match"] * (components.topic_match.score / 10)
        + WEIGHTS["source_reputation"] * computed.source_reputation
        + WEIGHTS["novelty"] * computed.novelty
        + WEIGHTS["recency_value"]
        * (components.recency_value.score / 10)
        * computed.recency_decay
        + WEIGHTS["effort_payoff"] * (components.effort_payoff.score / 10)
        + WEIGHTS["surprise"] * (components.surprise.score / 10)
    )
    return max(0, min(100, round(total)))


# --- rescore orchestration --------------------------------------------------


def _llm_components(breakdown: dict | None) -> ScoreOutput | None:
    """Pull the LLM ScoreOutput out of a stored breakdown, tolerating both the
    raw form (Phase 2) and the nested {"components": ...} form (Phase 3)."""
    if not breakdown:
        return None
    raw = breakdown.get("components", breakdown)
    if not isinstance(raw, dict) or "topic_match" not in raw:
        return None
    try:
        return ScoreOutput.model_validate(raw)
    except Exception:
        return None


def build_breakdown(
    components: ScoreOutput, computed: ComputedComponents, final: int
) -> dict:
    """The stored, explainable breakdown — powers "why this scored 87" (§7.4)."""
    return {
        "components": components.model_dump(),
        "computed": {
            "source_reputation": round(computed.source_reputation, 3),
            "novelty": round(computed.novelty, 3),
            "recency_decay": round(computed.recency_decay, 3),
            "is_news": computed.is_news,
        },
        "weights": WEIGHTS,
        "final": final,
    }


def score_item(conn: sqlite3.Connection, item: Item, persist: bool = True) -> Item:
    """Recompute an item's final score from its stored LLM components + live
    computed components. No LLM call (reputation/novelty/recency stay current)."""
    components = _llm_components(item.score_breakdown)
    if components is None:
        log.info("score.skip_no_components", item_id=item.id)
        return item

    blob = db.get_embedding(conn, item.id) if item.id else None
    novelty = (
        compute_novelty(conn, blob_to_embedding(blob), exclude_id=item.id)
        if blob
        else 1.0
    )
    reputation = compute_source_reputation(conn, item.domain)
    is_news = components.recency_value.score >= 7  # time-sensitive heuristic
    decay = compute_recency_decay(item.published_at, is_news)
    computed = ComputedComponents(reputation, novelty, decay, is_news)

    final = compute_final_score(components, computed)
    item.score = final
    item.score_breakdown = build_breakdown(components, computed, final)
    if persist and item.id:
        db.update_item_score(conn, item.id, final, item.score_breakdown)
    log.info("score.item", item_id=item.id, score=final)
    return item


def rescore_all(conn: sqlite3.Connection, status: str = "queued") -> int:
    """Re-score every item in ``status`` that has stored LLM components."""
    n = 0
    for item in db.list_items(conn, status=status, limit=100000):
        if _llm_components(item.score_breakdown) is not None:
            score_item(conn, item, persist=True)
            n += 1
    return n
