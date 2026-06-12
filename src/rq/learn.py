"""Feedback loop (§7.6): domain reputation + interest-drift detection.

``update_domain_stats`` recomputes a single domain's reputation after every
kill/keep/read. ``detect_interest_drift`` compares per-tag keep rates over the
last 60 days against interests.yaml and proposes add/remove suggestions for the
digest footer.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from .config import Interests
from .logging import get_logger
from .score import laplace_reputation

log = get_logger("learn")

# Interest-drift thresholds (§7.6).
_MIN_SAMPLE = 5          # need at least this many resolved items for a tag
_ADD_KEEP_RATE = 0.60    # kept this often + not in interests -> suggest adding
_REMOVE_KEEP_RATE = 0.30 # kept below this + in interests -> suggest removing
_POSITIVE = {"kept", "marked_read", "snoozed"}  # vs 'killed'


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


# --- interest drift (§7.6) --------------------------------------------------


@dataclass
class DriftSuggestion:
    action: str  # 'add' | 'remove'
    tag: str
    kept: int
    total: int

    @property
    def keep_rate(self) -> float:
        return self.kept / self.total if self.total else 0.0

    def to_text(self) -> str:
        if self.action == "add":
            return (
                f"you've kept {self.kept}/{self.total} articles tagged "
                f"{self.tag} but it's not in your interests — add it?"
            )
        return (
            f"you've kept only {self.kept}/{self.total} tagged {self.tag} "
            f"({self.keep_rate:.0%}) — drop it from your interests?"
        )


def _normalize(s: str) -> str:
    return s.replace("-", " ").replace("_", " ").lower().strip()


def _tag_in_interests(tag: str, active: list[str]) -> bool:
    t = _normalize(tag)
    for phrase in active:
        p = _normalize(phrase)
        if t in p or p in t:
            return True
    return False


def detect_interest_drift(
    conn: sqlite3.Connection, interests: Interests, days: int = 60
) -> list[DriftSuggestion]:
    """Per-tag keep rate over the last ``days`` days vs interests.yaml (§7.6)."""
    rows = conn.execute(
        """
        SELECT e.item_id, e.kind, i.tags_json
        FROM events e JOIN items i ON i.id = e.item_id
        WHERE e.kind IN ('killed','kept','marked_read','snoozed')
          AND e.at >= datetime('now', ?)
        ORDER BY e.at ASC
        """,
        (f"-{days} days",),
    ).fetchall()

    # Latest resolving event per item wins (avoid double-counting).
    latest: dict[int, tuple[str, list[str]]] = {}
    for r in rows:
        tags = json.loads(r["tags_json"]) if r["tags_json"] else []
        latest[r["item_id"]] = (r["kind"], tags)

    kept: dict[str, int] = defaultdict(int)
    killed: dict[str, int] = defaultdict(int)
    for kind, tags in latest.values():
        for tag in tags:
            (kept if kind in _POSITIVE else killed)[tag] += 1

    suggestions: list[DriftSuggestion] = []
    for tag in set(kept) | set(killed):
        total = kept[tag] + killed[tag]
        if total < _MIN_SAMPLE:
            continue
        rate = kept[tag] / total
        in_interests = _tag_in_interests(tag, interests.active)
        if not in_interests and rate >= _ADD_KEEP_RATE:
            suggestions.append(DriftSuggestion("add", tag, kept[tag], total))
        elif in_interests and rate < _REMOVE_KEEP_RATE:
            suggestions.append(DriftSuggestion("remove", tag, kept[tag], total))

    suggestions.sort(key=lambda s: s.total, reverse=True)
    return suggestions
