"""Enrichment (§7.3).

Phase 1 ships ``stub_enrich`` — a no-LLM placeholder so ``rq add`` stores a
complete-looking row with raw text. Phase 2 replaces ``enrich_item`` with the
three parallel LLM passes (summarize+tag on Haiku, pitch + score on Sonnet via
``asyncio.gather``), all routed through ``llm.complete``. Embedding is computed
locally in ``score.embed_text`` (no API call).
"""

from __future__ import annotations

from .config import Interests
from .logging import get_logger
from .schemas import ExtractedPage, Item

log = get_logger("enrich")


def stub_enrich(item: Item, page: ExtractedPage) -> Item:
    """Fill enrichment fields with cheap, deterministic placeholders (no LLM).

    Used in Phase 1 so the end-to-end ``add`` path is exercisable without an API
    key. Real summaries/pitch/score arrive in Phase 2.
    """
    text = page.text or ""
    first_sentence = text.strip().split(".")[0][:240] if text else ""

    item.tldr = (first_sentence or item.title or item.url)[:300]
    item.summary = None
    item.pitch = (
        "Paywalled — open original if you have access."
        if page.paywalled
        else None
    )
    item.tags = []
    item.score = None
    item.score_breakdown = None
    item.status = "queued"
    return item


async def enrich_item(
    item: Item,
    page: ExtractedPage,
    interests: Interests,
    recent_kept_titles: list[str],
) -> Item:
    """Real three-pass enrichment. Implemented in Phase 2."""
    raise NotImplementedError("real enrichment lands in Phase 2")
