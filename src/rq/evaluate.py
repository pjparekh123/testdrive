"""Eval harness (§8.4): score golden URLs and report drift.

For each entry in ``evals/golden.jsonl`` we use the cached enrichment (or ingest
if a fetcher is supplied), compute the current score, and report:
  * Spearman correlation between scores and my 1–5 ratings
  * a side-by-side pitch table flagging any banned phrases (§8.2)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from . import db, score as scoring
from .fetch import canonicalize_url
from .logging import get_logger
from .schemas import Item

log = get_logger("eval")


class GoldenEntry(BaseModel):
    url: str
    my_rating: int = Field(ge=1, le=5)
    notes: str = ""
    expected_tags: list[str] = Field(default_factory=list)


def load_golden(path: Path) -> list[GoldenEntry]:
    entries: list[GoldenEntry] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(GoldenEntry.model_validate_json(line))
    return entries


# --- Spearman (no scipy) ----------------------------------------------------


def _rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based, averaged over ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = math.sqrt(sum((a - mx) ** 2 for a in x))
    vy = math.sqrt(sum((b - my) ** 2 for b in y))
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / (vx * vy)


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) < 2:
        return float("nan")
    return _pearson(_rankdata(x), _rankdata(y))


# --- report -----------------------------------------------------------------


@dataclass
class EvalRow:
    url: str
    my_rating: int
    score: int | None
    pitch: str | None
    tags: list[str]
    expected_tags: list[str]
    banned: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | not_ingested | unenriched

    @property
    def tag_overlap(self) -> str:
        if not self.expected_tags:
            return "—"
        hit = set(self.tags) & set(self.expected_tags)
        return f"{len(hit)}/{len(self.expected_tags)}"


@dataclass
class EvalReport:
    rows: list[EvalRow]
    correlation: float
    scored: int
    banned_count: int


def _banned_in(pitch: str | None) -> list[str]:
    if not pitch:
        return []
    low = pitch.lower()
    return [p for p in scoring.BANNED_PHRASES if p in low]


async def run_eval(
    conn,
    entries: list[GoldenEntry],
    ingest_fn: Callable[[str], Awaitable[Item]] | None = None,
) -> EvalReport:
    rows: list[EvalRow] = []
    for e in entries:
        item = db.get_item(conn, canonicalize_url(e.url))
        status = "ok"
        if item is None and ingest_fn is not None:
            try:
                item = await ingest_fn(e.url)
            except Exception as ex:  # offline / fetch blocked
                log.warning("eval.ingest_failed", url=e.url, error=str(ex)[:160])
        if item is None:
            rows.append(EvalRow(e.url, e.my_rating, None, None, [], e.expected_tags, status="not_ingested"))
            continue

        # Compute the current score from stored components (no LLM call).
        item = scoring.score_item(conn, item, persist=False)
        if item.score is None:
            status = "unenriched"
        rows.append(
            EvalRow(
                url=e.url,
                my_rating=e.my_rating,
                score=item.score,
                pitch=item.pitch,
                tags=item.tags,
                expected_tags=e.expected_tags,
                banned=_banned_in(item.pitch),
                status=status,
            )
        )

    scored = [r for r in rows if r.score is not None]
    corr = spearman([r.score for r in scored], [r.my_rating for r in scored])
    banned_count = sum(1 for r in rows if r.banned)
    return EvalReport(rows=rows, correlation=corr, scored=len(scored), banned_count=banned_count)


def format_report(report: EvalReport) -> str:
    out: list[str] = []
    out.append(f"rq eval — {len(report.rows)} golden item(s)")
    out.append("=" * 78)
    out.append(f"{'#':>2}  {'rate':>4}  {'score':>5}  {'tags':>5}  pitch / status")
    out.append("-" * 78)
    for i, r in enumerate(report.rows, 1):
        score = "—" if r.score is None else str(r.score)
        if r.status == "not_ingested":
            body = "(not in queue — needs ingest)"
        elif r.status == "unenriched":
            body = "(no enrichment yet)"
        else:
            flag = "  ⚠ BANNED: " + ", ".join(r.banned) if r.banned else ""
            body = f"“{(r.pitch or '')[:54]}”{flag}"
        out.append(f"{i:>2}  {r.my_rating:>4}  {score:>5}  {r.tag_overlap:>5}  {body}")
    out.append("-" * 78)
    corr = "n/a" if math.isnan(report.correlation) else f"{report.correlation:+.2f}"
    target = "" if math.isnan(report.correlation) else (
        "  ✅ >0.7" if report.correlation > 0.7 else "  ⚠ below 0.7 target"
    )
    out.append(f"Spearman(score, rating) over {report.scored} scored item(s): {corr}{target}")
    out.append(f"Pitches with banned phrases: {report.banned_count}")
    return "\n".join(out)
