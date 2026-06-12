"""CLI surface (§10), built with typer. ``rq doctor`` is non-negotiable."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from . import db
from .config import get_settings, load_interests
from .ingest import add_batch, add_url
from .logging import configure_logging, get_logger
from .prompts import available_prompts
from .schemas import Item

app = typer.Typer(add_completion=False, help="Smart Reading Queue (rq)")
log = get_logger("cli")


def _boot():
    s = get_settings()
    configure_logging(s.log_level)
    return s


def _emit_status(conn, item_id: int, status: str, kind: str) -> Item | None:
    item = db.get_item(conn, item_id)
    if item is None:
        return None
    with conn:
        conn.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
        db.emit_event(conn, item_id, kind, None)
    item.status = status
    return item


# --- ingest -----------------------------------------------------------------


@app.command()
def add(url: str = typer.Argument(..., help="URL to add")):
    """Add a single URL."""
    _boot()
    item = asyncio.run(add_url(url, source="cli"))
    typer.echo(f"✅ #{item.id} {item.title or item.url}")
    if item.pitch:
        typer.echo(f"   {item.pitch}")
    if item.word_count:
        typer.echo(f"   {item.word_count} words · ~{item.read_minutes} min · {item.domain}")


@app.command("add-batch")
def add_batch_cmd(file: Path = typer.Argument(..., help="Newline-delimited URLs")):
    """Add newline-delimited URLs from a file."""
    _boot()
    urls = file.read_text().splitlines()
    items = asyncio.run(add_batch(urls))
    typer.echo(f"Added {len(items)} item(s).")


# --- read / browse ----------------------------------------------------------


@app.command(name="list")
def list_cmd(status: str = typer.Option(None, "--status", help="Filter by status")):
    """Show the queue."""
    _boot()
    conn = db.get_conn()
    try:
        items = db.list_items(conn, status=status)
    finally:
        conn.close()
    if not items:
        typer.echo("(empty)")
        return
    for it in items:
        score = f"{it.score:>3}" if it.score is not None else "  ·"
        typer.echo(f"[{score}] #{it.id:<4} {it.status:<7} {(it.title or it.url)[:70]}")


@app.command()
def show(key: str = typer.Argument(..., help="Item id or URL")):
    """Full record for one item."""
    _boot()
    conn = db.get_conn()
    try:
        item = db.get_item(conn, key)
    finally:
        conn.close()
    if item is None:
        typer.echo(f"not found: {key}")
        raise typer.Exit(1)
    d = item.model_dump()
    raw = d.pop("raw_text", None)
    typer.echo(json.dumps(d, indent=2, default=str))
    if raw:
        typer.echo(f"\n--- raw_text ({len(raw)} chars) ---\n{raw[:1000]}")


# --- status mutations -------------------------------------------------------


@app.command()
def kill(item_id: int):
    """Mark an item killed."""
    _boot()
    conn = db.get_conn()
    try:
        item = _emit_status(conn, item_id, "killed", "killed")
    finally:
        conn.close()
    typer.echo("🗑️ killed." if item else f"not found: {item_id}")


@app.command()
def keep(item_id: int):
    """Mark an item kept."""
    _boot()
    conn = db.get_conn()
    try:
        item = _emit_status(conn, item_id, "kept", "kept")
    finally:
        conn.close()
    typer.echo("kept." if item else f"not found: {item_id}")


@app.command()
def read(item_id: int):
    """Mark an item read."""
    _boot()
    conn = db.get_conn()
    try:
        item = _emit_status(conn, item_id, "read", "marked_read")
    finally:
        conn.close()
    typer.echo("read." if item else f"not found: {item_id}")


# --- deferred to later phases ----------------------------------------------


def _todo(phase: str):
    typer.echo(f"not implemented yet — lands in {phase}.")
    raise typer.Exit(1)


@app.command()
def find(query: str):
    """Full-text + embedding search (Phase 3)."""
    _todo("Phase 3")


@app.command()
def score(all: bool = typer.Option(False, "--all"), id: int = typer.Option(None, "--id")):
    """Rescore items (Phase 3)."""
    _todo("Phase 3")


@app.command()
def digest(dry_run: bool = typer.Option(False, "--dry-run")):
    """Generate (and send) the weekly digest (Phase 5)."""
    _todo("Phase 5")


@app.command()
def stats():
    """Queue health (Phase 6)."""
    _todo("Phase 6")


@app.command()
def export(format: str = typer.Option("json", "--format")):
    """Full dump (Phase 6)."""
    _todo("Phase 6")


@app.command(name="import")
def import_cmd(file: Path):
    """Backfill from Pocket/Instapaper (Phase 6)."""
    _todo("Phase 6")


@app.command(name="eval")
def eval_cmd():
    """Run prompts against golden.jsonl (Phase 3)."""
    _todo("Phase 3")


# --- doctor -----------------------------------------------------------------


@app.command()
def doctor():
    """Check config, secrets, DB, model access. Run this first when weird."""
    s = _boot()
    ok = True

    def line(label: str, good: bool, detail: str = "", critical: bool = True):
        nonlocal ok
        mark = "✅" if good else ("❌" if critical else "⚠️")
        if not good and critical:
            ok = False
        typer.echo(f" {mark} {label}{(' — ' + detail) if detail else ''}")

    typer.echo("rq doctor\n=========")

    # secrets / config (env-dependent — warnings, not hard failures)
    line("ANTHROPIC_API_KEY set", bool(s.anthropic_api_key), "" if s.anthropic_api_key else "missing (LLM passes will fail)", critical=False)
    line("TELEGRAM_BOT_TOKEN set", bool(s.telegram_bot_token), "" if s.telegram_bot_token else "missing (bot disabled)", critical=False)
    line("TELEGRAM_ALLOWED_USER_IDS", bool(s.allowed_user_ids), f"{len(s.allowed_user_ids)} id(s)", critical=False)

    # db + schema
    try:
        conn = db.connect(s.db_path)
        cur, req, current = db.check_schema(conn, s.migrations_dir)
        if cur < req:
            db.migrate(conn, s.migrations_dir)
            cur, req, current = db.check_schema(conn, s.migrations_dir)
        n = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
        conn.close()
        line("DB reachable + schema current", current, f"version {cur}/{req}, {n} item(s)")
    except Exception as e:
        line("DB reachable + schema current", False, str(e))

    # prompts
    prompts = available_prompts()
    needed = {"summarize", "pitch", "score_components"}
    line("prompts present", needed.issubset(set(prompts)), ", ".join(sorted(prompts)))

    # interests
    try:
        interests = load_interests()
        line("interests.yaml parses", True, f"{len(interests.active)} active, {len(interests.avoid)} avoid")
    except Exception as e:
        line("interests.yaml parses", False, str(e))

    # optional runtime deps
    try:
        import sentence_transformers  # noqa: F401
        line("embedding model importable", True, "all-MiniLM-L6-v2 (downloads on first use)")
    except ImportError:
        line("embedding model importable", False, "sentence-transformers missing")

    try:
        import playwright  # noqa: F401
        line("playwright importable", True, "fallback extraction available")
    except ImportError:
        line("playwright importable", False, "fallback disabled (non-fatal)", critical=False)

    typer.echo("\n" + ("all good ✅" if ok else "issues found ❌"))
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
