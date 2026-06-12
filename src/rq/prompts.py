"""Prompt loading. Prompts live in ``prompts/*.md`` and are loaded (and cached)
at startup. They contain literal JSON braces, so we substitute only the known
``{placeholder}`` keys instead of ``str.format``.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .config import get_settings


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load ``prompts/<name>.md`` once and cache it."""
    path = get_settings().prompts_dir / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text()


def render(template: str, **values: object) -> str:
    """Replace ``{key}`` for provided keys only; leave other braces untouched."""

    def repl(m: re.Match) -> str:
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)

    return re.sub(r"\{(\w+)\}", repl, template)


def load_and_render(name: str, **values: object) -> str:
    return render(load_prompt(name), **values)


def available_prompts() -> list[str]:
    d = get_settings().prompts_dir
    return sorted(p.stem for p in d.glob("*.md")) if d.exists() else []
