"""Feedback loop (§7.6, part 1): domain reputation.

``update_domain_stats`` recomputes a single domain's reputation from the current
items table. Called after every kill/keep/read event so reputation stays current.
(Interest-drift detection is Phase 6.)
"""

from __future__ import annotations

import sqlite3

from .logging import get_logger
from .score import laplace_reputation

log = get_logger("learn")


def update_domain_stats(conn: sqlite3.Connection, domain: str) -> float:
    """Recompute one domain's row in domain_stats. Returns the new reputation."""
    row = conn.execute(
        """
        SELECT
          COUNT(*)                                    AS total,
          COALESCE(SUM(status IN ('kept','read')), 0) AS kept_or_read,
          COALESCE(SUM(status = 'killed'), 0)         AS killed
        FROM items WHERE domain = ?
        """,
        (domain,),
    ).fetchone()

    total = row["total"]
    kept_or_read = row["kept_or_read"]
    killed = row["killed"]
    reputation = laplace_reputation(kept_or_read, killed)

    conn.execute(
        """
        INSERT INTO domain_stats (domain, total, kept_or_read, killed, reputation, updated_at)
        VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(domain) DO UPDATE SET
          total=excluded.total,
          kept_or_read=excluded.kept_or_read,
          killed=excluded.killed,
          reputation=excluded.reputation,
          updated_at=excluded.updated_at
        """,
        (domain, total, kept_or_read, killed, reputation),
    )
    log.info(
        "learn.domain_stats", domain=domain, total=total,
        kept_or_read=kept_or_read, killed=killed, reputation=round(reputation, 3),
    )
    return reputation
