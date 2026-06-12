"""Ingestion (§7.1): end-to-end add_url — dedupe -> fetch -> enrich -> store.

Phase 1 uses stub enrichment (no LLM). Every step writes an event; no silent
drops.
"""

from __future__ import annotations

import sqlite3

from . import db
from .config import get_settings
from .enrich import stub_enrich
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

    # 3. Stub enrichment (Phase 1). Real LLM passes land in Phase 2.
    item = stub_enrich(item, page)

    # 4. Store atomically + emit the `added` event.
    try:
        with conn:
            item_id = db.insert_item(conn, item)
            db.emit_event(conn, item_id, "added", {"via": source})
        item.id = item_id
    finally:
        if owns_conn:
            conn.close()

    log.info("ingest.added", url=canonical, item_id=item.id, words=page.word_count, ok=fetched_ok)
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
