"""Enrichment (§7.3): three LLM passes + a local embedding.

NOTE on ordering vs the spec: §7.3 calls these "three passes in parallel", but
the pitch prompt (§8.2) and score prompt (§8.3) both take the *summary* and
*tags* as input — so they cannot truly precede the summarize pass. We therefore
run summarize first, then pitch + score concurrently. All three are still driven
through a single ``asyncio.gather`` (pitch/score await the shared summarize
task), so the two independent passes overlap. Surfaced rather than silently
reinterpreted.

Embedding is computed locally via sentence-transformers (no API call), best
effort: if the model can't be loaded (e.g. offline), we log and return None so
ingestion still succeeds.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import numpy as np

from . import llm, score
from .config import Interests, get_settings
from .logging import get_logger
from .schemas import ExtractedPage, ScoreOutput, SummarizeOutput, PitchOutput

log = get_logger("enrich")

# Truncate very long bodies before sending to the LLM (keeps cost/latency sane).
_MAX_TEXT_CHARS = 16000


@dataclass
class EnrichmentResult:
    summary: str
    tldr: str
    tags: list[str]
    pitch: str
    score_components: ScoreOutput
    embedding: np.ndarray | None = field(default=None)


def _days_old(published_at: str | None) -> str:
    if not published_at:
        return "unknown"
    from datetime import datetime, timezone

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(published_at[: len(fmt) + 6], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return str((datetime.now(timezone.utc) - dt).days)
        except ValueError:
            continue
    return "unknown"


async def enrich(
    page: ExtractedPage,
    interests: Interests,
    recent_kept_titles: list[str],
) -> EnrichmentResult:
    """Run the three LLM passes (summarize -> pitch+score) and embed locally."""
    s = get_settings()
    text = (page.text or "")[:_MAX_TEXT_CHARS]

    # Pass 1: summarize + tag (Haiku). Pitch and score depend on its output.
    summarize_task = asyncio.create_task(
        llm.call(
            "summarize",
            {"title": page.title, "text": text},
            SummarizeOutput,
            s.summarize_model,
        )
    )

    async def do_pitch() -> PitchOutput:
        sm = await summarize_task
        return await llm.call(
            "pitch",
            {
                "title": page.title,
                "summary": sm.summary,
                "tags": ", ".join(sm.tags),
                "interests": ", ".join(interests.active) or "(none specified)",
            },
            PitchOutput,
            s.pitch_model,
        )

    async def do_score() -> ScoreOutput:
        sm = await summarize_task
        return await llm.call(
            "score_components",
            {
                "interests_yaml": interests.as_yaml(),
                "title": page.title,
                "tldr": sm.tldr,
                "summary": sm.summary,
                "tags": ", ".join(sm.tags),
                "word_count": page.word_count,
                "read_minutes": round((page.word_count or 0) / 230, 1),
                "published_at": page.published_at or "unknown",
                "days_old": _days_old(page.published_at),
                "recent_kept_titles": "\n".join(f"- {t}" for t in recent_kept_titles)
                or "(none yet)",
            },
            ScoreOutput,
            s.score_model,
        )

    summarize_out, pitch_out, score_out = await asyncio.gather(
        summarize_task, do_pitch(), do_score()
    )

    embedding = await _embed_best_effort(text or page.title)

    return EnrichmentResult(
        summary=summarize_out.summary,
        tldr=summarize_out.tldr,
        tags=summarize_out.tags,
        pitch=pitch_out.pitch,
        score_components=score_out,
        embedding=embedding,
    )


async def _embed_best_effort(text: str) -> np.ndarray | None:
    try:
        return await asyncio.to_thread(score.embed_text, text)
    except Exception as e:  # offline / model unavailable — non-fatal (§13)
        log.warning("enrich.embedding_unavailable", error=str(e)[:160])
        return None
