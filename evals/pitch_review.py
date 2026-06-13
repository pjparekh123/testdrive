"""Pitch-prompt review harness (Phase 7, req 1).

Pulls N random articles from your queue, shows each pitch side-by-side with the
article's title/summary/tags, and collects a 1–5 rating on three axes:
specificity, honesty, makes-me-want-to-open. Ratings are saved per prompt
*variant* so you can A/B prompt edits and re-eval.

Usage:
    # rate the pitches already stored on your items (no API calls):
    uv run python evals/pitch_review.py --n 30

    # regenerate pitches with an alternate prompt (prompts/<variant>.md) and rate:
    uv run python evals/pitch_review.py --n 30 --variant pitch_v1 --regenerate

    # aggregate every variant you've rated and check the >=4 bar:
    uv run python evals/pitch_review.py --report

The loop (per §15 day 7): rate the current prompt -> draft 3 variants in
prompts/ -> --regenerate + rate each -> --report -> ship the winner once all
three axes average >= 4.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rq import db
from rq.config import get_settings, load_interests
from rq.schemas import Item, PitchOutput

AXES = ("specificity", "honesty", "open")
RATINGS_DIR = Path(__file__).parent / "pitch_ratings"


def _sample(conn, n: int, need_inputs: bool) -> list[Item]:
    where = "summary IS NOT NULL AND tags_json IS NOT NULL" if need_inputs else "pitch IS NOT NULL"
    rows = conn.execute(
        f"SELECT * FROM items WHERE {where} ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    return [db.row_to_item(r) for r in rows]


async def _regen_pitch(item: Item, variant: str) -> str:
    from rq import llm  # local import so --report works without the SDK env

    s = get_settings()
    interests = load_interests()
    out = await llm.call(
        variant,
        {
            "title": item.title or item.url,
            "summary": item.summary or "",
            "tags": ", ".join(item.tags),
            "interests": ", ".join(interests.active) or "(none specified)",
        },
        PitchOutput,
        s.pitch_model,
    )
    return out.pitch


def _render(item: Item, pitch: str, idx: int, total: int) -> str:
    return (
        f"\n### [{idx}/{total}]  {item.title or item.url}\n"
        f"- **domain:** {item.domain}    **tags:** {', '.join(item.tags) or '—'}\n"
        f"- **summary:** {(item.summary or '—')[:400]}\n\n"
        f"> **PITCH:** {pitch}\n"
    )


def _ask(label: str) -> int | None:
    while True:
        raw = input(f"    {label} (1-5, or 's' to skip item, 'q' to quit): ").strip().lower()
        if raw == "q":
            raise KeyboardInterrupt
        if raw == "s":
            return None
        if raw in {"1", "2", "3", "4", "5"}:
            return int(raw)
        print("    please enter 1-5, 's', or 'q'.")


async def review(n: int, variant: str, regenerate: bool) -> None:
    conn = db.get_conn()
    try:
        items = _sample(conn, n, need_inputs=regenerate)
    finally:
        conn.close()
    if not items:
        print("No eligible items in the queue yet — backfill or add some first.")
        return

    RATINGS_DIR.mkdir(exist_ok=True)
    out_path = RATINGS_DIR / f"{variant}.jsonl"
    interactive = sys.stdin.isatty()
    print(f"\nReviewing {len(items)} item(s) for variant '{variant}'"
          + (" (regenerating pitches)" if regenerate else " (stored pitches)"))
    if not interactive:
        print("(no TTY — rendering only, not collecting ratings)\n")

    with out_path.open("a") if interactive else _devnull() as sink:
        for i, item in enumerate(items, 1):
            pitch = await _regen_pitch(item, variant) if regenerate else (item.pitch or "")
            print(_render(item, pitch, i, len(items)))
            if not interactive:
                continue
            try:
                scores = {axis: _ask(axis) for axis in AXES}
            except KeyboardInterrupt:
                print("\nstopping early — ratings so far are saved.")
                break
            if any(v is None for v in scores.values()):
                continue
            sink.write(json.dumps({"item_id": item.id, "url": item.url, "pitch": pitch, **scores}) + "\n")
            sink.flush()
    if interactive:
        print(f"\nsaved ratings to {out_path}")
        report()


class _devnull:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def write(self, *_):
        pass
    def flush(self):
        pass


def report() -> None:
    if not RATINGS_DIR.exists():
        print("no ratings yet — run a review first.")
        return
    print("\n# Pitch review — averages by variant\n")
    print(f"{'variant':<16} {'n':>3}  " + "  ".join(f"{a:>11}" for a in AXES) + "   verdict")
    print("-" * 72)
    for path in sorted(RATINGS_DIR.glob("*.jsonl")):
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        if not rows:
            continue
        means = {a: sum(r[a] for r in rows) / len(rows) for a in AXES}
        verdict = "✅ ships" if all(means[a] >= 4 for a in AXES) else "⤳ iterate"
        print(f"{path.stem:<16} {len(rows):>3}  "
              + "  ".join(f"{means[a]:>11.2f}" for a in AXES) + f"   {verdict}")


def main() -> None:
    p = argparse.ArgumentParser(description="Pitch-prompt review harness")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--variant", default="pitch", help="prompt name in prompts/<variant>.md")
    p.add_argument("--regenerate", action="store_true", help="re-run the pitch prompt (uses the API)")
    p.add_argument("--report", action="store_true", help="aggregate ratings and stop")
    args = p.parse_args()
    if args.report:
        report()
        return
    asyncio.run(review(args.n, args.variant, args.regenerate))


if __name__ == "__main__":
    main()
