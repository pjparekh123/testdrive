# Smart Reading Queue (`rq`)

A personal triage system for things you save but never read. One tap to save;
instant one-line pitches; a weekly **"kill or keep?"** digest that keeps the
queue *shrinking*. Telegram + CLI only (no web UI in v1).

See [`SPEC.md`](./SPEC.md) for the full design.

## Status

Built in phases (see §15 of the spec). **Phases 1–5 complete:** repo skeleton +
migrations + config + logging + `rq doctor` (1); real LLM enrichment via the
single wrapper (2); scoring system + domain reputation + `rq eval` harness (3);
Telegram bot with the kill/keep loop (4); weekly digest composer + in-process
scheduler, `rq digest --dry-run` / `--send` (5).

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

## Telegram bot

Drop the bot any URL from your phone and it saves it with a one-line pitch and
`[open] [snooze] [kill] [read]` buttons.

**Setup**

1. **Create the bot.** In Telegram, message [@BotFather](https://t.me/BotFather),
   send `/newbot`, and follow the prompts. It returns a token like
   `123456789:AAE…`. Put it in `.env` as `TELEGRAM_BOT_TOKEN`.
2. **Find your user id.** Message [@userinfobot](https://t.me/userinfobot) (or
   `@RawDataBot`) and copy the numeric `Id`. Put it in `.env` as
   `TELEGRAM_ALLOWED_USER_IDS` (comma-separated for multiple people). The bot
   **silently ignores** anyone not on this list.
3. **Run it.** `uv run rq bot` (foreground, long-polling). `rq doctor` will show
   whether the token and allowed-user ids are set.

Commands: `/start` `/help` `/add <url>` `/queue` `/stats` `/digest_now`
`/kill_old`. Any message containing one or more URLs is treated as an add.

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
