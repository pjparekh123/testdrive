"""Type-safe configuration (``pydantic-settings`` + ``.env``) and the
hot-reloadable ``interests.yaml`` loader.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Loaded from environment / ``.env``. See ``.env.example``."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""  # comma-separated ints

    db_path: Path = Path("./rq.db")
    digest_cron: str = "0 9 * * SUN"
    digest_goal: int = 30  # target queue size shown in the digest footer
    local_tz: str = "America/Los_Angeles"
    log_level: str = "INFO"

    # Models (§5). Bulk summarize/tag on Haiku; pitch/score on Sonnet.
    summarize_model: str = "claude-haiku-4-5-20251001"
    pitch_model: str = "claude-sonnet-4-6"
    score_model: str = "claude-sonnet-4-6"

    # Hard monthly cost cap in USD (§18). New enrichments queue when exceeded.
    monthly_cost_cap_usd: float = 5.0

    interests_path: Path = REPO_ROOT / "interests.yaml"
    prompts_dir: Path = REPO_ROOT / "prompts"
    migrations_dir: Path = REPO_ROOT / "migrations"

    @property
    def allowed_user_ids(self) -> set[int]:
        raw = self.telegram_allowed_user_ids.strip()
        if not raw:
            return set()
        return {int(x) for x in raw.split(",") if x.strip()}


class Interests(BaseModel):
    """Parsed ``interests.yaml``. Part of the scoring prompt (§12)."""

    active: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    goals_this_quarter: list[str] = Field(default_factory=list)

    def as_yaml(self) -> str:
        """Render back to YAML for embedding in prompts."""
        return yaml.safe_dump(
            {
                "active": self.active,
                "avoid": self.avoid,
                "goals_this_quarter": self.goals_this_quarter,
            },
            sort_keys=False,
        ).strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_interests(path: Path | None = None) -> Interests:
    """Read ``interests.yaml`` fresh each call (hot-reloaded, not cached)."""
    p = path or get_settings().interests_path
    if not p.exists():
        return Interests()
    data = yaml.safe_load(p.read_text()) or {}
    return Interests.model_validate(data)
