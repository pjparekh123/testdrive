from __future__ import annotations

from rq import scheduler


def test_build_scheduler_parses_cron_and_registers_job():
    sched = scheduler.build_scheduler(lambda: None, "0 9 * * SUN", "America/Los_Angeles")
    # Job lives in the pending set until start(); the trigger parsed Sunday 9am.
    pending = list(sched._pending_jobs)
    assert len(pending) == 1
    job = pending[0][0]  # (job, jobstore_alias, replace_existing)
    trigger = str(job.trigger)
    assert "day_of_week='sun'" in trigger and "hour='9'" in trigger


async def test_scheduler_start_computes_next_run():
    sched = scheduler.build_scheduler(lambda: None, "0 9 * * SUN", "America/Los_Angeles")
    sched.start()
    try:
        job = sched.get_job(scheduler.JOB_ID)
        assert job is not None
        assert job.next_run_time is not None  # a concrete next Sunday 9am
    finally:
        sched.shutdown(wait=False)
