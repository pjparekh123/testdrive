"""Telegram bot integration tests.

Handlers are driven directly with mocked Update/Context objects (no real
Telegram connection); the polling entrypoint is tested with
Application.run_polling mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import Application

from rq import bot, db
from rq.config import get_settings
from rq.schemas import Item

ALLOWED = 42
DENIED = 999


@pytest.fixture
def bot_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(ALLOWED))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bot.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _msg_update(user_id: int, text: str):
    placeholder = MagicMock()
    placeholder.edit_text = AsyncMock()
    msg = MagicMock()
    msg.text = text
    msg.reply_text = AsyncMock(return_value=placeholder)
    update = MagicMock()
    update.effective_user.id = user_id
    update.message = msg
    return update, msg, placeholder


def _cb_update(user_id: int, data: str):
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = q
    return update, q


def _fake_item(**kw):
    base = dict(
        id=1, url="https://blog.example.com/ships", canonical_url="https://blog.example.com/ships",
        domain="blog.example.com", title="Ships", pitch="Maps every container ship lost at sea in 2023.",
        read_minutes=7.0, status="queued",
    )
    base.update(kw)
    return Item(**base)


# --- URL extraction ---------------------------------------------------------


def test_extract_urls_multiple_and_trailing_punctuation():
    text = "see https://a.com/x, and (https://b.com/y) plus https://a.com/x again."
    assert bot.extract_urls(text) == ["https://a.com/x", "https://b.com/y"]


def test_extract_urls_none():
    assert bot.extract_urls("no links here") == []


# --- auth gate --------------------------------------------------------------


async def test_unauthorized_user_is_ignored_silently(bot_env):
    update, msg, _ = _msg_update(DENIED, "https://a.com/x")
    await bot.on_message(update, MagicMock())
    msg.reply_text.assert_not_awaited()  # no reply at all


async def test_unauthorized_callback_ignored(bot_env):
    update, q = _cb_update(DENIED, "kill:1")
    await bot.on_callback(update, MagicMock())
    q.answer.assert_not_awaited()


# --- add flow (processing -> edit to pitch) ---------------------------------


async def test_url_message_shows_processing_then_edits_to_pitch(bot_env, monkeypatch):
    async def fake_add(url, source="telegram"):
        return _fake_item()

    monkeypatch.setattr(bot, "add_url", fake_add)

    update, msg, placeholder = _msg_update(ALLOWED, "check https://blog.example.com/ships")
    await bot.on_message(update, MagicMock())

    # Immediate placeholder, then a single edit to the pitch with buttons.
    assert msg.reply_text.await_args_list[0].args[0] == "📥 processing…"
    placeholder.edit_text.assert_awaited_once()
    edit = placeholder.edit_text.await_args
    assert "Maps every container ship" in edit.args[0]
    assert "7 min" in edit.args[0] and "blog.example.com" in edit.args[0]
    assert isinstance(edit.kwargs["reply_markup"], InlineKeyboardMarkup)


async def test_add_command(bot_env, monkeypatch):
    monkeypatch.setattr(bot, "add_url", AsyncMock(return_value=_fake_item()))
    update, msg, placeholder = _msg_update(ALLOWED, "/add https://blog.example.com/ships")
    ctx = MagicMock()
    ctx.args = ["https://blog.example.com/ships"]
    await bot.add_cmd(update, ctx)
    placeholder.edit_text.assert_awaited_once()


async def test_add_failure_edits_placeholder(bot_env, monkeypatch):
    async def boom(url, source="telegram"):
        raise RuntimeError("fetch blocked")

    monkeypatch.setattr(bot, "add_url", boom)
    update, msg, placeholder = _msg_update(ALLOWED, "https://blog.example.com/ships")
    await bot.on_message(update, MagicMock())
    assert "couldn't add" in placeholder.edit_text.await_args.args[0]


# --- callbacks --------------------------------------------------------------


async def test_kill_callback_updates_db(bot_env):
    conn = db.get_conn()
    item_id = db.insert_item(conn, _fake_item(id=None))
    conn.commit()
    conn.close()

    update, q = _cb_update(ALLOWED, f"kill:{item_id}")
    await bot.on_callback(update, MagicMock())

    q.answer.assert_awaited()
    q.edit_message_text.assert_awaited()

    conn = db.get_conn()
    item = db.get_item(conn, item_id)
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (item_id,))]
    conn.close()
    assert item.status == "killed"
    assert "killed" in kinds


async def test_snooze_callback_moves_to_kept(bot_env):
    conn = db.get_conn()
    item_id = db.insert_item(conn, _fake_item(id=None))
    conn.commit()
    conn.close()

    update, q = _cb_update(ALLOWED, f"snooze:{item_id}")
    await bot.on_callback(update, MagicMock())

    conn = db.get_conn()
    item = db.get_item(conn, item_id)
    kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events WHERE item_id=?", (item_id,))]
    conn.close()
    assert item.status == "kept"
    assert "snoozed" in kinds


# --- polling entrypoint (run_polling mocked) --------------------------------


def test_run_invokes_run_polling(bot_env, monkeypatch):
    calls = []
    monkeypatch.setattr(Application, "run_polling", lambda self, *a, **k: calls.append(self))
    bot.run()
    assert len(calls) == 1  # built the app and started polling exactly once
