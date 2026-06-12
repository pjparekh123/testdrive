"""Backfill from Pocket (HTML) and Instapaper (CSV) exports (§10, §15 day 6).

Both have well-known formats:
  * Pocket    — a Netscape-bookmark HTML file of ``<a href=...>`` links.
  * Instapaper — a CSV with a ``URL`` column (header: URL,Title,Selection,Folder).

Parsed URLs are backfilled through the normal ingest path (full enrichment),
so the cost cap (§18) applies just like any other add.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from . import db
from .fetch import canonicalize_url
from .ingest import add_url
from .logging import get_logger

log = get_logger("import")


class _PocketParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and href.startswith(("http://", "https://")):
            self.urls.append(href)


def parse_pocket(path: Path) -> list[str]:
    parser = _PocketParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return _dedupe(parser.urls)


def parse_instapaper(path: Path) -> list[str]:
    urls: list[str] = []
    # utf-8-sig handles the BOM Instapaper sometimes includes.
    with path.open(newline="", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        url_key = next((k for k in (reader.fieldnames or []) if k and k.strip().lower() == "url"), None)
        if url_key is None:
            return []
        for row in reader:
            url = (row.get(url_key) or "").strip()
            if url.startswith(("http://", "https://")):
                urls.append(url)
    return _dedupe(urls)


def parse_export(path: Path) -> list[str]:
    """Dispatch by extension (.html/.htm -> Pocket, .csv -> Instapaper)."""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return parse_pocket(path)
    if suffix == ".csv":
        return parse_instapaper(path)
    raise ValueError(f"unrecognized export format: {path.name} (use .html or .csv)")


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


@dataclass
class ImportReport:
    total: int
    added: int
    duplicates: int
    failed: int


async def import_file(
    path: Path,
    conn=None,
    on_progress: Callable[[int, int], None] | None = None,
) -> ImportReport:
    """Parse an export and backfill each URL through the ingest pipeline."""
    urls = parse_export(path)
    own = conn is None
    conn = conn or db.get_conn()
    added = duplicates = failed = 0
    try:
        for i, url in enumerate(urls, 1):
            try:
                existed = db.item_by_canonical(conn, canonicalize_url(url)) is not None
                await add_url(url, source="import", conn=conn)
                duplicates += existed
                added += not existed
            except Exception as e:
                failed += 1
                log.warning("import.item_failed", url=url, error=str(e)[:160])
            if on_progress:
                on_progress(i, len(urls))
    finally:
        if own:
            conn.close()
    log.info("import.done", total=len(urls), added=added, duplicates=duplicates, failed=failed)
    return ImportReport(total=len(urls), added=added, duplicates=duplicates, failed=failed)
