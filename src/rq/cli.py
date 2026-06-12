"""CLI surface (§10), built with typer. ``rq doctor`` is non-negotiable."""

from __future__ import annotations

import asyncio
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
    _print_record(item)


def _print_record(item: Item) -> None:
    def row(label: str, value) -> None:
        if value is None or value == "" or value == []:
            return
        typer.echo(f"  {label:<14} {value}")

    score = f"{item.score}" if item.score is not None else "— (Phase 3)"
    typer.echo(f"\n#{item.id}  [{item.status}]  score {score}")
    typer.echo("─" * 60)
    row("title", item.title)
    row("pitch", f"“{item.pitch}”" if item.pitch else None)
    row("tldr", item.tldr)
    row("tags", ", ".join(item.tags) if item.tags else None)
    row("url", item.canonical_url or item.url)
    row("domain", item.domain)
    row("author", item.author)
    row("published", item.published_at)
    wc = f"{item.word_count} words · ~{item.read_minutes} min" if item.word_count else None
    row("length", wc)
    row("added", item.added_at)
    row("added_via", item.added_via)

    if item.summary:
        typer.echo("\n  summary")
        for ln in _wrap(item.summary, 70):
            typer.echo(f"    {ln}")

    if item.score_breakdown:
        typer.echo("\n  score components (raw LLM, pre-weighting)")
        for name, comp in item.score_breakdown.items():
            if isinstance(comp, dict) and "score" in comp:
                typer.echo(f"    {name:<15} {comp['score']}/10 — {comp.get('reason','')}")

    if item.raw_text:
        typer.echo(f"\n  raw_text       {len(item.raw_text)} chars (first 300):")
        typer.echo(f"    {item.raw_text[:300].strip()}…")


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width)


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
    """Checklist: config valid, DB exists + migrations current, API key present.

    Does NOT call the Anthropic API. Run this first when anything's weird.
    """
    s = _boot()
    ok = True

    def line(label: str, good: bool, detail: str = ""):
        nonlocal ok
        if not good:
            ok = False
        typer.echo(f" {'✅' if good else '❌'} {label}{(' — ' + detail) if detail else ''}")

    typer.echo("rq doctor\n=========")

    # 1. config valid (settings load + interests.yaml + prompts present)
    try:
        interests = load_interests()
        prompts = set(available_prompts())
        needed = {"summarize", "pitch", "score_components"}
        missing = needed - prompts
        if missing:
            line("config valid", False, f"missing prompts: {', '.join(sorted(missing))}")
        else:
            line(
                "config valid",
                True,
                f"db_path={s.db_path}, {len(interests.active)} interests, {len(prompts)} prompts",
            )
    except Exception as e:
        line("config valid", False, str(e))

    # 2. database exists
    db_exists = s.db_path.exists()
    line("database exists", db_exists, str(s.db_path) if db_exists else f"{s.db_path} not found (run `rq add` to create)")

    # 3. migrations current
    try:
        conn = db.connect(s.db_path)
        cur, req, current = db.check_schema(conn, s.migrations_dir)
        conn.close()
        if db_exists:
            line("migrations current", current, f"schema v{cur}/{req}")
        else:
            line("migrations current", True, f"will apply v1..{req} on first run")
    except Exception as e:
        line("migrations current", False, str(e))

    # 4. ANTHROPIC_API_KEY present (presence only — no API call)
    line("ANTHROPIC_API_KEY present", bool(s.anthropic_api_key), "" if s.anthropic_api_key else "missing")

    typer.echo("\n" + ("all checks passed ✅" if ok else "issues found ❌"))
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
