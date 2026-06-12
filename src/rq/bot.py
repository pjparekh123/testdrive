"""Telegram bot surface (§11), python-telegram-bot v21+ (async).

Commands: /start /help /add /queue /stats /digest_now /kill_old.
Any message containing a URL is treated as an add. After adding, the bot replies
within seconds with the pitch + inline [open] [snooze] [kill] [read] buttons.

Security: only user IDs in TELEGRAM_ALLOWED_USER_IDS are answered; everyone else
is ignored silently (no reply at all).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import db, learn
from .config import Settings, get_settings
from .ingest import add_url
from .logging import configure_logging, get_logger
from .schemas import Item

log = get_logger("bot")

# Robust-enough URL matcher; trailing punctuation is trimmed afterwards.
_URL_RE = re.compile(r"https?://[^\s<>\"'()]+", re.IGNORECASE)
_TRAILING = ".,;:!?'\")]}>"


def extract_urls(text: str) -> list[str]:
    """All URLs in a message, de-duplicated, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _URL_RE.findall(text or ""):
        url = raw.rstrip(_TRAILING)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


# --- auth -------------------------------------------------------------------


def _authorized(update: Update, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    user = update.effective_user
    return bool(user and user.id in s.allowed_user_ids)


# --- presentation -----------------------------------------------------------


def pitch_message(item: Item) -> str:
    headline = item.pitch or item.title or item.canonical_url or item.url
    read = f"{item.read_minutes:g} min" if item.read_minutes else "—"
    return f"{headline}\n⏱ {read} · {item.domain}"


def item_keyboard(item_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(
        [
            [
                b("📖 open", callback_data=f"open:{item_id}"),
                b("💤 snooze", callback_data=f"snooze:{item_id}"),
            ],
            [
                b("🗑️ kill", callback_data=f"kill:{item_id}"),
                b("✓ read", callback_data=f"mark_read:{item_id}"),
            ],
        ]
    )


def kill_candidate_keyboard(item_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(
        [[b("🗑️ kill", callback_data=f"kill:{item_id}"),
          b("💚 keep", callback_data=f"snooze:{item_id}")]]
    )


# --- shared status mutation -------------------------------------------------


def _set_status(conn, item: Item, status: str, kind: str, payload: dict | None = None) -> None:
    conn.execute("UPDATE items SET status=? WHERE id=?", (status, item.id))
    db.emit_event(conn, item.id, kind, payload)
    learn.update_domain_stats(conn, item.domain)
    conn.commit()


# --- ingest reply (the latency moment) --------------------------------------


async def _process_url(message, url: str) -> None:
    """Send '📥 processing…' immediately, then edit to the pitch when done."""
    placeholder = await message.reply_text("📥 processing…")
    try:
        item = await add_url(url, source="telegram")
    except Exception as e:  # never leave the placeholder hanging
        log.warning("bot.add_failed", url=url, error=str(e)[:200])
        await placeholder.edit_text(f"⚠️ couldn't add {url}\n{str(e)[:150]}")
        return
    await placeholder.edit_text(pitch_message(item), reply_markup=item_keyboard(item.id))


# --- handlers ---------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "📚 Smart Reading Queue\n\n"
        "Drop me any URL and I'll save it with a one-line pitch.\n"
        "Try /help for commands."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "Commands:\n"
        "• send any URL — save it (multiple per message ok)\n"
        "• /add <url> — save a URL\n"
        "• /queue — top of your queue\n"
        "• /stats — queue health\n"
        "• /digest_now — preview the digest\n"
        "• /kill_old — review stale items\n"
        "• /help — this message\n\n"
        "On each saved item: 📖 open · 💤 snooze · 🗑️ kill · ✓ read"
    )


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    urls = extract_urls(" ".join(context.args or []))
    if not urls:
        await update.message.reply_text("usage: /add <url>")
        return
    for url in urls:
        await _process_url(update.message, url)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return  # silent — unauthorized users get nothing
    urls = extract_urls(update.message.text or "")
    if not urls:
        await update.message.reply_text("Send me a URL to save it, or /help.")
        return
    for url in urls:
        await _process_url(update.message, url)


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    conn = db.get_conn()
    try:
        items = db.list_items(conn, status="queued", limit=10)
    finally:
        conn.close()
    if not items:
        await update.message.reply_text("queue is empty 🎉")
        return
    lines = ["📋 Top of the queue\n"]
    for it in items:
        score = it.score if it.score is not None else "—"
        lines.append(f"[{score}] {(it.pitch or it.title or it.url)[:64]}")
    await update.message.reply_text("\n".join(lines))


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    conn = db.get_conn()
    try:
        await update.message.reply_text(_stats_text(conn))
    finally:
        conn.close()


async def digest_now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    conn = db.get_conn()
    try:
        top = [i for i in db.list_items(conn, status="queued", limit=3) if i.score is not None]
    finally:
        conn.close()
    msg = ["📚 Digest preview (full composer lands in Phase 5)\n"]
    if not top:
        msg.append("nothing scored yet — add and score some items first.")
    else:
        for it in top:
            msg.append(f"✨ {(it.pitch or it.title)} — {it.read_minutes or '?'} min · {it.domain}")
    await update.message.reply_text("\n".join(msg))


async def kill_old_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    conn = db.get_conn()
    try:
        candidates = db.kill_candidates(conn)
    finally:
        conn.close()
    if not candidates:
        await update.message.reply_text("nothing stale to review 🎉")
        return
    await update.message.reply_text("🗑️ Stale items — kill or keep?")
    for it in candidates:
        await update.message.reply_text(
            f"{(it.title or it.url)[:80]}\n{it.domain}",
            reply_markup=kill_candidate_keyboard(it.id),
        )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    query = update.callback_query
    action, _, sid = (query.data or "").partition(":")
    if not sid.isdigit():
        await query.answer("bad action")
        return
    item_id = int(sid)

    conn = db.get_conn()
    try:
        item = db.get_item(conn, item_id)
        if item is None:
            await query.answer("item not found")
            return

        if action == "open":
            db.emit_event(conn, item_id, "opened", None)
            conn.commit()
            await query.answer("opening")
            await query.message.reply_text(item.url)

        elif action == "kill":
            _set_status(conn, item, "killed", "killed")
            await query.answer("🗑️ killed")
            await query.edit_message_text(f"🗑️ killed: {item.pitch or item.title or item.url}")

        elif action == "snooze":
            until = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            _set_status(conn, item, "kept", "snoozed", {"until": until})
            await query.answer("💤 snoozed 30 days")
            await query.edit_message_text(f"💤 snoozed until {until}: {item.title or item.url}")

        elif action == "mark_read":
            _set_status(conn, item, "read", "marked_read")
            await query.answer("✓ marked read")
            await query.edit_message_text(f"✓ read: {item.pitch or item.title or item.url}")

        else:
            await query.answer("unknown action")
    finally:
        conn.close()


# --- stats text -------------------------------------------------------------


def _stats_text(conn) -> str:
    rows = conn.execute("SELECT status, COUNT(*) AS c FROM items GROUP BY status").fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    total = sum(counts.values())
    killed = counts.get("killed", 0)
    resolved = killed + counts.get("kept", 0) + counts.get("read", 0)
    rate = f"{killed / resolved:.0%}" if resolved else "n/a"
    lines = [f"📊 Queue health — {total} items"]
    for st in ("queued", "kept", "read", "killed", "archived"):
        if counts.get(st):
            lines.append(f"  {st}: {counts[st]}")
    lines.append(f"  kill rate: {rate}")
    return "\n".join(lines)


# --- wiring -----------------------------------------------------------------


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("digest_now", digest_now_cmd))
    app.add_handler(CommandHandler("kill_old", kill_old_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))


def build_application(token: str | None = None) -> Application:
    s = get_settings()
    app = ApplicationBuilder().token(token or s.telegram_bot_token).build()
    register_handlers(app)
    return app


def run() -> None:
    """Run the bot in the foreground (long-polling)."""
    s = get_settings()
    configure_logging(s.log_level)
    log.info("bot.start", allowed_users=len(s.allowed_user_ids))
    app = build_application()
    app.run_polling()
