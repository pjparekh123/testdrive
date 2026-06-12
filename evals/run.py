"""Eval harness runner (§8.4). Thin wrapper around ``rq.evaluate``.

Usage:  uv run python evals/run.py   (or: rq eval)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rq import db
from rq.config import get_settings
from rq.evaluate import format_report, load_golden, run_eval
from rq.ingest import add_url

GOLDEN = Path(__file__).parent / "golden.jsonl"


def main() -> None:
    get_settings()
    conn = db.get_conn()
    try:
        entries = load_golden(GOLDEN)
        report = asyncio.run(run_eval(conn, entries, ingest_fn=add_url))
        conn.commit()
        print(format_report(report))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
