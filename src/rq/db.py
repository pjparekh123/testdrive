"""SQLite access layer: WAL connection, append-only migration runner, and
row<->``Item`` helpers. No raw dicts cross out of here — callers get ``Item``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, get_settings
from .logging import get_logger
from .schemas import Item

log = get_logger("db")

_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")

# Python 3.12 deprecated the implicit datetime<->TIMESTAMP adapters. Register an
# explicit writer (ISO strings); reads come back as strings and Pydantic coerces.
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat(sep=" "))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- connection -------------------------------------------------------------


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


# --- migrations -------------------------------------------------------------


def available_migrations(migrations_dir: Path) -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for p in sorted(migrations_dir.glob("*.sql")):
        m = _MIGRATION_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    out.sort(key=lambda t: t[0])
    return out


def required_version(migrations_dir: Path) -> int:
    migs = available_migrations(migrations_dir)
    return migs[-1][0] if migs else 0


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not row:
        return 0
    r = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return r["v"] or 0


def migrate(conn: sqlite3.Connection, migrations_dir: Path) -> int:
    """Apply pending migrations in order. Append-only: each file bumps
    ``schema_version`` itself. Returns the resulting version.
    """
    applied = current_version(conn)
    for num, path in available_migrations(migrations_dir):
        if num <= applied:
            continue
        log.info("migrate.apply", version=num, file=path.name)
        with conn:  # transaction
            conn.executescript(path.read_text())
        applied = current_version(conn)
    return applied


def check_schema(conn: sqlite3.Connection, migrations_dir: Path) -> tuple[int, int, bool]:
    cur = current_version(conn)
    req = required_version(migrations_dir)
    return cur, req, cur >= req


def get_conn(settings: Settings | None = None) -> sqlite3.Connection:
    """Connect and ensure the schema is current (auto-applies pending
    append-only migrations)."""
    s = settings or get_settings()
    conn = connect(s.db_path)
    migrate(conn, s.migrations_dir)
    return conn


# --- row <-> Item -----------------------------------------------------------


def row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        url=row["url"],
        canonical_url=row["canonical_url"],
        domain=row["domain"],
        title=row["title"],
        author=row["author"],
        published_at=row["published_at"],
        added_at=row["added_at"],
        fetched_at=row["fetched_at"],
        raw_text=row["raw_text"],
        word_count=row["word_count"],
        read_minutes=row["read_minutes"],
        summary=row["summary"],
        tldr=row["tldr"],
        pitch=row["pitch"],
        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
        score=row["score"],
        score_breakdown=(
            json.loads(row["score_breakdown_json"])
            if row["score_breakdown_json"]
            else None
        ),
        status=row["status"],
        added_via=row["added_via"],
        last_surfaced_at=row["last_surfaced_at"],
        surface_count=row["surface_count"],
    )


def get_item(conn: sqlite3.Connection, key: int | str) -> Item | None:
    if isinstance(key, int) or str(key).isdigit():
        row = conn.execute("SELECT * FROM items WHERE id=?", (int(key),)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM items WHERE url=? OR canonical_url=?", (key, key)
        ).fetchone()
    return row_to_item(row) if row else None


def item_by_canonical(conn: sqlite3.Connection, canonical_url: str) -> Item | None:
    row = conn.execute(
        "SELECT * FROM items WHERE canonical_url=?", (canonical_url,)
    ).fetchone()
    return row_to_item(row) if row else None


def list_items(
    conn: sqlite3.Connection, status: str | None = None, limit: int = 100
) -> list[Item]:
    if status:
        rows = conn.execute(
            "SELECT * FROM items WHERE status=? ORDER BY score DESC NULLS LAST, added_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY added_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [row_to_item(r) for r in rows]


def insert_item(
    conn: sqlite3.Connection, item: Item, embedding: bytes | None = None
) -> int:
    cur = conn.execute(
        """
        INSERT INTO items (
            url, canonical_url, domain, title, author, published_at,
            fetched_at, raw_text, word_count, read_minutes, summary, tldr,
            pitch, tags_json, embedding, score, score_breakdown_json,
            status, added_via, surface_count
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            item.url,
            item.canonical_url,
            item.domain,
            item.title,
            item.author,
            item.published_at,
            item.fetched_at,
            item.raw_text,
            item.word_count,
            item.read_minutes,
            item.summary,
            item.tldr,
            item.pitch,
            json.dumps(item.tags) if item.tags else None,
            embedding,
            item.score,
            json.dumps(item.score_breakdown) if item.score_breakdown else None,
            item.status,
            item.added_via,
            item.surface_count,
        ),
    )
    return int(cur.lastrowid)


def update_enrichment(
    conn: sqlite3.Connection, item_id: int, item: Item, embedding: bytes | None = None
) -> None:
    conn.execute(
        """
        UPDATE items SET
            summary=?, tldr=?, pitch=?, tags_json=?, embedding=?,
            score=?, score_breakdown_json=?, status=?
        WHERE id=?
        """,
        (
            item.summary,
            item.tldr,
            item.pitch,
            json.dumps(item.tags) if item.tags else None,
            embedding,
            item.score,
            json.dumps(item.score_breakdown) if item.score_breakdown else None,
            item.status,
            item_id,
        ),
    )


def emit_event(
    conn: sqlite3.Connection,
    item_id: int | None,
    kind: str,
    payload: dict | None = None,
) -> None:
    """Record an interaction. Every failure writes an event — no silent drops."""
    conn.execute(
        "INSERT INTO events (item_id, kind, payload_json, at) VALUES (?,?,?,?)",
        (
            item_id,
            kind,
            json.dumps(payload) if payload else None,
            utcnow(),
        ),
    )
    log.info("event", item_id=item_id, kind=kind)
