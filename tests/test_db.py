from __future__ import annotations

from pathlib import Path

import pytest

from rq import db
from rq.config import get_settings

REAL_MIGRATIONS = get_settings().migrations_dir


# --- against the real migrations/ ------------------------------------------


def test_fresh_db_starts_at_version_zero(tmp_path):
    conn = db.connect(tmp_path / "fresh.db")
    assert db.current_version(conn) == 0
    conn.close()


def test_migrate_applies_pending_and_creates_schema(tmp_path):
    conn = db.connect(tmp_path / "m.db")
    new_version = db.migrate(conn, REAL_MIGRATIONS)
    assert new_version == db.required_version(REAL_MIGRATIONS) >= 1
    # Core tables from 001 exist.
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"items", "events", "domain_stats", "schema_version"} <= tables
    conn.close()


def test_migrate_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "idem.db")
    v1 = db.migrate(conn, REAL_MIGRATIONS)
    # Running again applies nothing and keeps the same version.
    v2 = db.migrate(conn, REAL_MIGRATIONS)
    assert v1 == v2
    rows = conn.execute("SELECT COUNT(*) AS c FROM schema_version").fetchone()["c"]
    assert rows == 1  # version 1 recorded exactly once
    conn.close()


def test_check_schema_reports_behind(tmp_path):
    conn = db.connect(tmp_path / "behind.db")
    cur, req, ok = db.check_schema(conn, REAL_MIGRATIONS)
    assert cur == 0 and req >= 1 and ok is False
    db.migrate(conn, REAL_MIGRATIONS)
    cur, req, ok = db.check_schema(conn, REAL_MIGRATIONS)
    assert cur == req and ok is True
    conn.close()


# --- runner mechanics with a synthetic migrations dir ----------------------


def _write(d: Path, name: str, sql: str) -> None:
    (d / name).write_text(sql)


def test_runner_applies_in_order_and_only_pending(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(
        migrations,
        "001_init.sql",
        "CREATE TABLE a (id INTEGER PRIMARY KEY);\n"
        "CREATE TABLE schema_version (version INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_version VALUES (1);\n",
    )
    _write(
        migrations,
        "002_add_b.sql",
        "CREATE TABLE b (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO schema_version VALUES (2);\n",
    )

    assert [n for n, _ in db.available_migrations(migrations)] == [1, 2]
    assert db.required_version(migrations) == 2

    conn = db.connect(tmp_path / "syn.db")

    # Apply only 001 first (simulate a DB already at v1).
    conn.executescript((migrations / "001_init.sql").read_text())
    conn.commit()
    assert db.current_version(conn) == 1

    # Runner should now apply only the pending 002.
    assert db.migrate(conn, migrations) == 2
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"a", "b"} <= tables
    conn.close()


def test_available_migrations_ignores_non_numbered(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    _write(migrations, "001_init.sql", "SELECT 1;")
    _write(migrations, "notes.sql", "SELECT 1;")
    _write(migrations, "README.md", "ignore me")
    assert [n for n, _ in db.available_migrations(migrations)] == [1]
