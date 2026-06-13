# Smart Reading Queue (`rq`)

A personal triage system for things you save but never read. One tap to save;
instant one-line pitches; a weekly **"kill or keep?"** digest that keeps the
queue *shrinking*. Telegram + CLI only (no web UI in v1).

See [`SPEC.md`](./SPEC.md) for the full design.

## Status

Built in phases (see §15 of the spec). **Phases 1–7 complete:** repo skeleton +
migrations + config + logging + `rq doctor` (1); real LLM enrichment via the
single wrapper (2); scoring system + domain reputation + `rq eval` harness (3);
Telegram bot with the kill/keep loop (4); weekly digest composer + in-process
scheduler (5); interest-drift suggestions, Pocket/Instapaper import, monthly
cost cap, `rq stats`, and nightly backups (6); Fly.io deploy + `/health` +
pitch-review harness (7). Remaining day-7 polish (live pitch iteration, first
real Sunday digest, retro) runs on your deployed instance — see below.

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

## Importing existing bookmarks

Backfill from a Pocket or Instapaper export — each URL goes through full
enrichment (and the §18 cost cap applies):

```bash
uv run rq import ~/Downloads/pocket_export.html      # Pocket (HTML)
uv run rq import ~/Downloads/instapaper-export.csv   # Instapaper (CSV)
```

## Backups

Nightly logical dump, rotated weekly (`scripts/backup.sh`). Add to crontab:

```cron
# nightly at 03:00
0 3 * * *  cd /path/to/reading-queue && DB_PATH=./rq.db ./scripts/backup.sh
```

Each run writes `backup/rq-YYYYMMDD-HHMMSS.sql.gz` and deletes dumps older than
7 days (`RETENTION_DAYS` to change).

## Deploy to Fly.io

The bot, the weekly-digest scheduler, and a `/health` endpoint all run in one
always-on machine, with SQLite (and the embedding-model cache) on a persistent
volume.

```bash
fly launch --no-deploy                       # creates the app from fly.toml
fly volumes create rq_data --size 1          # persistent /data (DB + model cache)

fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  TELEGRAM_BOT_TOKEN=123456:ABC... \
  TELEGRAM_ALLOWED_USER_IDS=123456789

fly deploy
fly logs                                      # watch it boot + apply migrations
curl https://<app>.fly.dev/health             # {"status":"ok","version":"..."}
```

Notes:
- `auto_stop_machines = false` — the process must stay up for Telegram
  long-polling and the Sunday cron.
- Playwright's browser isn't baked into the image (the fetch fallback degrades
  gracefully per §13); the image is already large because of torch.
- The image carries `LOCAL_TZ`/`DIGEST_CRON` via `[env]`; override with
  `fly secrets`/`fly.toml` as needed.

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
