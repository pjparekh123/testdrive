"""Ingestion (§7.1): end-to-end add_url — dedupe -> fetch -> enrich -> store.

Real enrichment (Phase 2): three LLM passes + local embedding. The final score
is left to Phase 3 — we store the raw LLM score components in
``score_breakdown_json`` and leave ``score`` NULL for now.
"""

from __future__ import annotations

import sqlite3

from . import db, score as scoring
from .config import get_settings, load_interests
from .enrich import enrich
from .fetch import canonicalize_url, domain_of, fetch_and_extract
from .logging import get_logger
from .schemas import Item

log = get_logger("ingest")

WORDS_PER_MINUTE = 230


async def add_url(url: str, source: str = "cli", conn: sqlite3.Connection | None = None) -> Item:
    """End-to-end: dedupe -> fetch -> extract -> (stub) enrich -> store."""
    settings = get_settings()
    owns_conn = conn is None
    conn = conn or db.get_conn(settings)

    canonical = canonicalize_url(url)
    domain = domain_of(canonical)

    # 1. Dedupe on canonical_url. Return existing; leave surface_count alone so a
    #    re-add doesn't rescue a stale item from the kill list.
    existing = db.item_by_canonical(conn, canonical)
    if existing is not None:
        db.emit_event(conn, existing.id, "added", {"duplicate": True, "via": source})
        conn.commit()
        log.info("ingest.duplicate", url=canonical, item_id=existing.id)
        if owns_conn:
            conn.close()
        return existing

    # 2. Fetch + extract (httpx + trafilatura; no Playwright fallback yet).
    page = await fetch_and_extract(canonical)
    fetched_ok = bool(page.text) and page.word_count > 0
    read_minutes = round(page.word_count / WORDS_PER_MINUTE, 2) if page.word_count else None

    item = Item(
        url=url,
        canonical_url=canonical,
        domain=domain,
        title=page.title,
        author=page.author,
        published_at=page.published_at,
        fetched_at=db.utcnow() if fetched_ok else None,
        raw_text=page.text or None,
        word_count=page.word_count or None,
        read_minutes=read_minutes,
        status="queued",
        added_via=source if source in ("telegram", "cli", "shortcut") else "cli",
    )

    # 3. Real enrichment (3 LLM passes + embedding). Only attempted when we have
    #    article text. Failures leave the row queued + unenriched (no crash).
    embedding_blob: bytes | None = None
    enriched = False
    if fetched_ok:
        try:
            interests = load_interests()
            recent = db.recent_kept_titles(conn)
            result = await enrich(page, interests, recent)
            item.summary = result.summary
            item.tldr = result.tldr
            item.tags = result.tags
            item.pitch = result.pitch
            # Store raw LLM components now; final 0–100 score is Phase 3.
            item.score_breakdown = result.score_components.model_dump()
            item.score = None
            if result.embedding is not None:
                embedding_blob = scoring.embedding_to_blob(result.embedding)
            enriched = True
        except Exception as e:
            log.warning("ingest.enrich_failed", url=canonical, error=str(e)[:300])

    # 4. Store atomically + emit events.
    try:
        with conn:
            item_id = db.insert_item(conn, item, embedding=embedding_blob)
            db.emit_event(conn, item_id, "added", {"via": source})
            if enriched:
                db.emit_event(conn, item_id, "enriched", {"tags": item.tags})
        item.id = item_id
    finally:
        if owns_conn:
            conn.close()

    log.info(
        "ingest.added", url=canonical, item_id=item.id, words=page.word_count,
        fetched=fetched_ok, enriched=enriched,
    )
    return item


async def add_batch(urls: list[str], source: str = "cli") -> list[Item]:
    """Add newline-delimited URLs sequentially, reusing one connection."""
    conn = db.get_conn()
    out: list[Item] = []
    try:
        for raw in urls:
            u = raw.strip()
            if not u or u.startswith("#"):
                continue
            try:
                out.append(await add_url(u, source=source, conn=conn))
            except Exception as e:  # one bad URL shouldn't abort the batch
                log.warning("ingest.batch_error", url=u, error=str(e))
    finally:
        conn.close()
    return out
