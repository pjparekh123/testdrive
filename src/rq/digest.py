"""Weekly digest (§7.5): select items, compose the Telegram message, send it.

The composed message is MarkdownV2 (so it renders with bold headers in Telegram);
``md_to_preview`` strips the escaping for a clean terminal dry-run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import db
from .config import get_settings
from .logging import get_logger
from .schemas import Item

log = get_logger("digest")


@dataclass
class DigestSelection:
    read_this: list[Item]
    skim: list[Item]
    kill_these: list[Item]

    @property
    def surfaced(self) -> list[Item]:
        return self.read_this + self.skim + self.kill_these


@dataclass
class DigestStats:
    queue_size: int
    goal: int


# --- selection (§7.5 rules) -------------------------------------------------


def select_items(conn) -> DigestSelection:
    """Three lists:
    * read_this  — top 3 queued, score ≥ 70, not surfaced in the last 14 days
    * skim       — next 5 queued in the 50–69 band
    * kill_these — up to 7 stale items (>14d old, surfaced ≥2, never opened)
    """
    read_this = [
        db.row_to_item(r)
        for r in conn.execute(
            """
            SELECT * FROM items
            WHERE status='queued' AND score >= 70
              AND (last_surfaced_at IS NULL
                   OR last_surfaced_at < datetime('now', '-14 days'))
            ORDER BY score DESC, added_at ASC
            LIMIT 3
            """
        )
    ]
    skim = [
        db.row_to_item(r)
        for r in conn.execute(
            """
            SELECT * FROM items
            WHERE status='queued' AND score BETWEEN 50 AND 69
            ORDER BY score DESC, added_at ASC
            LIMIT 5
            """
        )
    ]
    kill_these = db.kill_candidates(conn, limit=7)
    return DigestSelection(read_this, skim, kill_these)


# --- MarkdownV2 helpers -----------------------------------------------------

_MD_SPECIAL = set(r"_*[]()~`>#+-=|{}.!\\")


def escape_md(text) -> str:
    """Escape MarkdownV2 special characters in dynamic content."""
    return "".join("\\" + c if c in _MD_SPECIAL else c for c in str(text))


def md_to_preview(md: str) -> str:
    """Strip MarkdownV2 escaping + bold/italic markers for a clean terminal
    preview (the sent message keeps them so Telegram renders the formatting)."""
    out = re.sub(r"\\([_*\[\]()~`>#+\-=|{}.!\\])", r"\1", md)
    return out.replace("*", "").replace("_", "")


def _fmt_minutes(read_minutes: float | None) -> str:
    if not read_minutes:
        return "?"
    return f"{max(1, round(read_minutes))} min"


def _days_ago(added_at, now: datetime) -> int | None:
    if not added_at:
        return None
    dt = added_at
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


# --- composition ------------------------------------------------------------


def compose_message(
    read_this: list[Item],
    skim: list[Item],
    kill_these: list[Item],
    stats: DigestStats,
    now: datetime | None = None,
    suggestions: list | None = None,
    notice: str | None = None,
) -> str:
    """Produce the MarkdownV2 digest message text (§7.5 format)."""
    now = now or datetime.now(timezone.utc)
    L: list[str] = ["📚 *Weekly Reading Queue*"]

    if not (read_this or skim or kill_these):
        L.append("")
        L.append("Your queue is clear — nothing to surface this week\\. 🎉")
        L.append("")
        L.append(_footer(stats))
        _append_extras(L, suggestions, notice)
        return "\n".join(L)

    # ✨ Read this
    L.append("")
    L.append("✨ *Read this*")
    if read_this:
        for i, it in enumerate(read_this, 1):
            headline = escape_md(it.pitch or it.title or it.url)
            L.append(f"{i}\\. {headline}")
            L.append(f"   _{_fmt_minutes(it.read_minutes)} · {escape_md(it.domain)}_")
    else:
        L.append("_nothing meets the bar this week_")

    # 👀 Skim if curious
    if skim:
        L.append("")
        L.append("👀 *Skim if curious*")
        for it in skim:
            title = escape_md((it.title or it.pitch or it.url)[:70])
            L.append(f"• {title} — {_fmt_minutes(it.read_minutes)} — {escape_md(it.domain)}")

    # 🗑️ Kill these?
    if kill_these:
        L.append("")
        L.append("🗑️ *Kill these?* _\\(stale, never opened\\)_")
        for it in kill_these:
            n = _days_ago(it.added_at, now)
            age = f" — saved {n}d ago" if n is not None else ""
            title = escape_md((it.title or it.url)[:60])
            L.append(f"• {title} — {escape_md(it.domain)}{age}")

    L.append("")
    L.append(_footer(stats))
    _append_extras(L, suggestions, notice)
    return "\n".join(L)


def _footer(stats: DigestStats) -> str:
    return f"📥 queue: *{stats.queue_size}* → goal: under {stats.goal} by month\\-end"


def _append_extras(L: list[str], suggestions: list | None, notice: str | None) -> None:
    """Interest-drift suggestions (§7.6) and the cost-cap notice (§18)."""
    for sg in (suggestions or [])[:3]:
        L.append("")
        L.append(f"💡 {escape_md(sg.to_text())}")
    if notice:
        L.append("")
        L.append(f"💸 {escape_md(notice)}")


# --- inline keyboard (reuses the bot's callback actions) --------------------


def build_keyboard(sel: DigestSelection) -> InlineKeyboardMarkup | None:
    """One keyboard for the digest message. Buttons map to the bot's existing
    callbacks (open/mark_read/snooze/kill/keep) via ``action:item_id``."""
    b = InlineKeyboardButton
    rows: list[list[InlineKeyboardButton]] = []
    for i, it in enumerate(sel.read_this, 1):
        rows.append([
            b(f"{i} 📖 open", callback_data=f"open:{it.id}"),
            b(f"{i} ✓ read", callback_data=f"mark_read:{it.id}"),
            b(f"{i} 💤", callback_data=f"snooze:{it.id}"),
        ])
    for it in sel.skim:
        rows.append([b(f"📖 {it.domain[:16]}", callback_data=f"open:{it.id}")])
    for it in sel.kill_these:
        rows.append([
            b(f"🗑️ {it.domain[:12]}", callback_data=f"kill:{it.id}"),
            b("💚 keep", callback_data=f"keep:{it.id}"),
            b("📖 read", callback_data=f"open:{it.id}"),
        ])
    return InlineKeyboardMarkup(rows) if rows else None


# --- send -------------------------------------------------------------------


def _mark_surfaced(conn, items: list[Item], now: datetime) -> None:
    for it in items:
        conn.execute(
            "UPDATE items SET surface_count = surface_count + 1, last_surfaced_at = ? WHERE id = ?",
            (now, it.id),
        )
        db.emit_event(conn, it.id, "surfaced", None)


async def send_digest(conn=None, bot=None, dry_run: bool = False, now: datetime | None = None) -> str:
    """Compose; if not dry-run, send to allowed users and mark items surfaced
    (surface_count++ , last_surfaced_at, 'surfaced' event). Returns the message.
    """
    s = get_settings()
    own = conn is None
    conn = conn or db.get_conn()
    now = now or db.utcnow()
    try:
        sel = select_items(conn)
        qsize = conn.execute(
            "SELECT COUNT(*) AS c FROM items WHERE status='queued'"
        ).fetchone()["c"]

        from . import learn
        from .config import load_interests

        suggestions = learn.detect_interest_drift(conn, load_interests())
        spend = db.get_month_spend(conn)
        notice = None
        if spend >= s.monthly_cost_cap_usd:
            notice = (
                f"monthly cost cap (${s.monthly_cost_cap_usd:.2f}) reached — "
                "new saves are queued without summaries until next month."
            )
        text = compose_message(
            sel.read_this, sel.skim, sel.kill_these, DigestStats(qsize, s.digest_goal),
            now=now, suggestions=suggestions, notice=notice,
        )
        if dry_run:
            return text

        if bot is None:
            from telegram import Bot

            bot = Bot(s.telegram_bot_token)
        keyboard = build_keyboard(sel)
        for uid in s.allowed_user_ids:
            await bot.send_message(
                chat_id=uid, text=text, parse_mode="MarkdownV2", reply_markup=keyboard
            )
        with conn:
            _mark_surfaced(conn, sel.surfaced, now)
        log.info("digest.sent", recipients=len(s.allowed_user_ids), surfaced=len(sel.surfaced))
        return text
    finally:
        if own:
            conn.close()
