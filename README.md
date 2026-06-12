# Smart Reading Queue (`rq`)

A personal triage system for things you save but never read. One tap to save;
instant one-line pitches; a weekly **"kill or keep?"** digest that keeps the
queue *shrinking*. Telegram + CLI only (no web UI in v1).

See [`SPEC.md`](./SPEC.md) for the full design.

## Status

Built in phases (see §15 of the spec). **Phase 1 complete:** repo skeleton,
SQLite migrations, config, structured logging, `rq doctor`, and `rq add`
end-to-end with stub enrichment.

## Quickstart

```bash
uv sync --extra dev --python 3.12     # install deps into .venv
cp .env.example .env                   # fill in ANTHROPIC_API_KEY etc.
uv run rq doctor                       # check config, DB, model access
uv run rq add https://example.com/some-article
uv run rq show 1
```

## Layout

```
prompts/      LLM prompts as versioned .md files, loaded at startup
migrations/   append-only numbered SQL migrations
src/rq/       the single Python app (CLI, bot, scheduler share one core)
tests/        pytest + vcr.py cassettes (no live API calls in CI)
evals/        golden.jsonl + harness for prompt-quality regression
```

## Development

```bash
uv run pytest            # run the test suite (replays cassettes)
uv run rq doctor         # smoke check
```

Ground rules: every LLM call goes through `src/rq/llm.py`; Pydantic schemas are
the contract between modules; prompts live in `prompts/*.md`; migrations are
append-only.

## License

MIT
