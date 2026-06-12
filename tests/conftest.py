from __future__ import annotations

from pathlib import Path

import pytest

from rq import db
from rq.config import get_settings


@pytest.fixture
def conn(tmp_path: Path):
    """A migrated SQLite connection backed by a throwaway file."""
    settings = get_settings()
    c = db.connect(tmp_path / "test.db")
    db.migrate(c, settings.migrations_dir)
    yield c
    c.close()
