"""In-process scheduler (§5, §12): APScheduler parses DIGEST_CRON and fires the
weekly digest. Runs in the same process/event loop as the bot.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .config import get_settings
from .digest import send_digest
from .logging import get_logger

log = get_logger("scheduler")

JOB_ID = "weekly_digest"


def build_scheduler(send_fn, cron: str, tz: str) -> AsyncIOScheduler:
    """Create an AsyncIOScheduler with the digest job on the given cron."""
    timezone = ZoneInfo(tz)
    scheduler = AsyncIOScheduler(timezone=timezone)
    trigger = CronTrigger.from_crontab(cron, timezone=timezone)
    scheduler.add_job(send_fn, trigger, id=JOB_ID, name="weekly digest")
    return scheduler


async def _digest_job(bot) -> None:
    """Run one digest send against a fresh connection (so the long-lived
    scheduler never holds a connection open between weeks)."""
    conn = db.get_conn()
    try:
        await send_digest(conn=conn, bot=bot, dry_run=False)
    except Exception as e:  # never let a digest failure kill the scheduler
        log.warning("scheduler.digest_failed", error=str(e)[:200])
    finally:
        conn.close()


async def on_post_init(application) -> None:
    """python-telegram-bot post-init hook: start the digest scheduler inside the
    bot's running event loop, sending through the bot's own client."""
    s = get_settings()
    scheduler = build_scheduler(
        lambda: _digest_job(application.bot), s.digest_cron, s.local_tz
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    job = scheduler.get_job(JOB_ID)
    log.info("scheduler.started", cron=s.digest_cron, tz=s.local_tz,
             next_run=str(getattr(job, "next_run_time", None)))
