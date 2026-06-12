# Smart Reading Queue — SPEC

> A personal triage system for things you save but never read. Adds friction in the right places (encourages killing items), removes friction in the wrong places (one tap to save, summaries are instant). The system gets smarter about your taste over time.

-----

## 1. Vision

Most “read later” apps are write-only: a graveyard of good intentions. This one inverts that. Every week it asks **“kill or keep?”** on stale items and surfaces the 1–3 things future-you would actually thank present-you for reading. Each item arrives with a one-line pitch that makes the open-or-skip decision easy and honest.

**Success looks like:** within 4 weeks, the digest is the most-tapped notification on your phone, your queue size is *shrinking*, and the kill/keep ratio is roughly 60/40.

-----

## 2. Non-goals

We are explicitly **not** building:

- A highlighter / annotation tool (Readwise exists)
- A full RSS reader (Feedly exists)
- A shared social bookmarking app (this is personal)
- A “read it now” reader view (open the original URL; don’t rebuild Reader Mode)
- A web UI in v1 (Telegram + CLI only)
- Anything that requires running a browser to add an item

-----

## 3. User stories

1. **Add (10 seconds, on phone).** I’m reading Twitter, see a link, tap share → Telegram bot, get a ✅ + 1-line pitch back within 8 seconds.
1. **Digest (Sunday 9am).** Telegram message: 3 “read this” with pitches, up to 5 “skim if curious”, and a “kill these?” section with inline buttons.
1. **Kill/keep loop.** I tap Kill or Keep on stale items in <2 seconds each. Feels like clearing notifications — satisfying.
1. **Ask (CLI).** From my laptop: `rq find "that thing about container ships"` returns the URL.
1. **Tune (file).** I edit `interests.yaml` to tell the system what I care about right now. Next digest reflects it.

-----

## 4. Architecture

```
            ┌──────────────┐
   phone ──►│ Telegram Bot │──┐
            └──────────────┘  │
            ┌──────────────┐  │      ┌─────────────────┐    ┌──────────┐
   laptop ─►│     CLI      │──┼─────►│  Core (Python)  │───►│  SQLite  │
            └──────────────┘  │      └─────────────────┘    └──────────┘
            ┌──────────────┐  │              │
   cron ───►│  Scheduler   │──┘              ▼
            └──────────────┘         ┌─────────────────┐
                                     │ Anthropic + ST  │
                                     │ (summarize,     │
                                     │  tag, score,    │
                                     │  embed)         │
                                     └─────────────────┘
```

**Single process.** No microservices. Everything is one Python app with multiple entry points (CLI, bot, scheduler).

-----

## 5. Stack & dependencies

|Concern   |Choice                                      |Why                                                                                      |
|----------|--------------------------------------------|-----------------------------------------------------------------------------------------|
|Language  |Python 3.12+                                |Best Anthropic SDK + ML ecosystem                                                        |
|DB        |SQLite (WAL mode)                           |Single-file, zero ops, plenty for personal scale                                         |
|HTTP      |`httpx`                                     |Async, modern                                                                            |
|Extraction|`trafilatura` primary, `playwright` fallback|Trafilatura handles 90% of pages cleanly                                                 |
|LLM       |`anthropic` SDK                             |`claude-sonnet-4-6` for scoring/pitch, `claude-haiku-4-5-20251001` for bulk summarize/tag|
|Embeddings|`sentence-transformers` (all-MiniLM-L6-v2)  |Local, free, good enough for novelty detection                                           |
|Validation|`pydantic` v2                               |Strict JSON from LLM outputs                                                             |
|Bot       |`python-telegram-bot` v21+                  |Mature, async                                                                            |
|Scheduler |`apscheduler`                               |In-process cron                                                                          |
|Config    |`pydantic-settings` + `.env`                |Type-safe config                                                                         |
|Tests     |`pytest` + `pytest-asyncio` + `vcr.py`      |Replay HTTP for deterministic tests                                                      |
|Logging   |`structlog`                                 |JSON logs, easy to grep                                                                  |

**Hard requirement:** every LLM call goes through one wrapper module that handles retries, JSON parsing, schema validation, and logging. No raw SDK calls scattered through the codebase.

-----

## 6. Data model

```sql
-- Items: one row per saved URL
CREATE TABLE items (
  id            INTEGER PRIMARY KEY,
  url           TEXT NOT NULL UNIQUE,
  canonical_url TEXT,                  -- after redirect + utm strip
  domain        TEXT NOT NULL,
  title         TEXT,
  author        TEXT,
  published_at  TIMESTAMP,             -- from page metadata if available
  added_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fetched_at    TIMESTAMP,
  raw_text      TEXT,                  -- extracted article body
  word_count    INTEGER,
  read_minutes  REAL,                  -- word_count / 230
  summary       TEXT,                  -- 3–5 sentences
  tldr          TEXT,                  -- 1 sentence, neutral
  pitch         TEXT,                  -- ≤15 words, opinionated, the magic
  tags_json     TEXT,                  -- JSON array of strings
  embedding     BLOB,                  -- numpy float32, 384 dims
  score         INTEGER,               -- 0–100, current "should you read this"
  score_breakdown_json TEXT,           -- per-component scores + reasoning
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','read','killed','kept','archived')),
  added_via     TEXT,                  -- 'telegram','cli','shortcut'
  last_surfaced_at TIMESTAMP,
  surface_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_added_at ON items(added_at);
CREATE INDEX idx_items_domain ON items(domain);

-- Events: every user interaction, for learning + analytics
CREATE TABLE events (
  id        INTEGER PRIMARY KEY,
  item_id   INTEGER REFERENCES items(id) ON DELETE CASCADE,
  kind      TEXT NOT NULL CHECK (kind IN
              ('added','fetched','enriched','surfaced',
               'opened','killed','kept','marked_read','snoozed')),
  payload_json TEXT,                   -- optional details
  at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_item ON events(item_id);
CREATE INDEX idx_events_kind_at ON events(kind, at);

-- Domain stats: derived, recomputed on schedule
CREATE TABLE domain_stats (
  domain        TEXT PRIMARY KEY,
  total         INTEGER NOT NULL DEFAULT 0,
  kept_or_read  INTEGER NOT NULL DEFAULT 0,
  killed        INTEGER NOT NULL DEFAULT 0,
  reputation    REAL,                  -- 0.0–1.0, Laplace-smoothed
  updated_at    TIMESTAMP
);

-- Schema migrations
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES (1);
```

**Migration policy:** every schema change ships as a numbered SQL file in `migrations/`. App refuses to start if `schema_version` is behind.

-----

## 7. Component specs

### 7.1 Ingestion (`ingest.py`)

```python
async def add_url(url: str, source: str = "cli") -> Item:
    """End-to-end: dedupe → fetch → extract → enrich → store."""
```

**Behavior:**

1. Normalize URL: follow redirects, strip `utm_*`, `fbclid`, `gclid`, trailing `/`.
1. Check `canonical_url` for duplicate. If exists, bump `surface_count = 0`, return existing.
1. Fetch (see 7.2). If fetch fails, store row with `status='queued'`, `raw_text=NULL`, and a queued retry.
1. Enrich (see 7.3). Atomic transaction: row only commits with all enrichment fields populated, OR row commits with `status='queued'` and an error event.
1. Emit `added` event.
1. Return the Item.

**Latency budget:** p50 < 6s, p95 < 12s. Most of the budget is extraction + LLM.

### 7.2 Extraction (`fetch.py`)

```python
async def fetch_and_extract(url: str) -> ExtractedPage:
    """Returns title, author, published_at, text, word_count."""
```

**Chain:**

1. `httpx` GET with realistic UA, 10s timeout, follow redirects (max 5).
1. If `text/html`, run `trafilatura.extract(..., favor_recall=True, with_metadata=True)`.
1. If word count < 200 OR extraction returns None, fall back to Playwright (headless Chromium, wait for `networkidle`, then re-run trafilatura on rendered HTML).
1. If still < 200 words, store what we have and mark `needs_review=True` in payload.

**Edge cases to handle on day 1:**

- PDFs (`application/pdf`): extract with `pypdf`, treat as article.
- YouTube URLs: fetch transcript via `youtube-transcript-api`, set `author = channel`, `title = video title`.
- Twitter/X URLs: don’t try to render; store URL with title = author + first 80 chars if available from oEmbed.
- Paywalled (detect by `<meta name="article:content_tier" content="locked">` or word count < 200 after Playwright): store with `paywalled=True`; pitch becomes “Paywalled — open original if you have access.”

### 7.3 Enrichment (`enrich.py`)

Runs three LLM passes in parallel (asyncio.gather):

1. **Summarize + tag** (`haiku-4-5`): returns `summary`, `tldr`, `tags`.
1. **Pitch** (`sonnet-4-6`): returns the one-line opinionated hook.
1. **Score components** (`sonnet-4-6`): returns the breakdown (topic match, novelty rationale, etc.). Pure-numeric components (recency, source reputation, effort/payoff) are computed in Python and combined with LLM outputs to produce final `score`.

Embedding is computed locally (no API call).

All three passes use the LLM wrapper which retries on JSON parse failure (1 retry with a “Your previous output was not valid JSON. Return only the JSON object.” nudge), then hard-fails.

### 7.4 Scoring (`score.py`)

**Final score = weighted sum, 0–100.**

|Component        |Weight|Source        |Notes                                                                                  |
|-----------------|-----:|--------------|---------------------------------------------------------------------------------------|
|Topic match      |30    |LLM           |Compare tags + summary to `interests.yaml`                                             |
|Source reputation|20    |Computed      |Laplace-smoothed kept/(kept+killed) for domain, prior 0.5 with α=3                     |
|Novelty          |15    |Computed      |1 - max cosine similarity vs. last 50 items’ embeddings                                |
|Recency value    |15    |LLM           |“Does this need to be read soon, or is it evergreen?” + decay if news-y and >7 days old|
|Effort/payoff    |10    |Computed + LLM|`min(1, expected_value / read_minutes)`                                                |
|Surprise         |10    |LLM           |Does this challenge user’s typical reading?                                            |

**Re-score weekly** on `queued` items so reputation/novelty stay current.

Score breakdown is **stored**. The digest shows “why this scored 87” if you tap. Explainability builds trust.

### 7.5 Digest (`digest.py`)

Runs weekly (default Sunday 09:00 local). Composes a single Telegram message:

```
📚 Weekly Reading Queue

✨ Read this
1. [pitch] — 7 min — domain.com
   [open] [mark read] [snooze]
2. ...
3. ...

👀 Skim if curious
• Title — 3 min — domain.com [open]
• ...

🗑️ Kill these? (saved 18 days ago, never opened)
• Title — domain.com [kill] [keep] [read now]
• ...

queue: 47 → goal: under 30 by month-end
```

**Selection rules:**

- “Read this”: top 3 by score from `queued`, score ≥ 70, not surfaced in last 14 days.
- “Skim”: next 5 by score, score 50–69.
- “Kill these”: up to 7 items where `added_at < now - 14d` AND `surface_count >= 2` AND never opened.

Every action updates `events` and triggers re-scoring of related items (same domain, same tags).

### 7.6 Feedback loop (`learn.py`)

Two things that learn:

1. **Domain reputation** updates after every kill/keep/read event.
1. **Interest drift detection**: weekly, compare tag distribution of kept-items vs. killed-items over last 60 days. If a tag’s keep-rate drops below 30%, suggest removing it from `interests.yaml`; if a tag appears frequently in kept items but isn’t in interests, suggest adding it. Suggestions land in the digest footer.

No ML training loop. The rubric stays interpretable.

-----

## 8. Prompt specs

All prompts live in `prompts/` as `.md` files, loaded at startup. Version them in git.

### 8.1 `prompts/summarize.md`

```
You are summarizing an article for a personal reading queue. Be neutral, dense, and concrete.

ARTICLE TITLE: {title}
ARTICLE TEXT:
{text}

Return JSON only, matching this schema exactly:
{
  "tldr": "One sentence, ≤25 words, factual not promotional.",
  "summary": "3–5 sentences. Cover the central claim, key evidence, and any surprising finding. No filler phrases like 'this article discusses'.",
  "tags": ["3–6 lowercase tags, single words or hyphenated, e.g. neuroscience, urban-planning, llm-evals"]
}

Rules:
- Never use the phrases "this article", "the author argues", "in this piece".
- If the article is mostly opinion, say so in the summary.
- If the article is thin (listicle, news brief), keep summary to 2 sentences.
- Return JSON only. No prose, no markdown fences.
```

### 8.2 `prompts/pitch.md` — **the magic**

```
You write one-line pitches for a personal reading queue. The pitch decides whether someone opens the article or skips it. Be specific, slightly opinionated, and hint at the surprising bit.

INPUT:
- Title: {title}
- Summary: {summary}
- Tags: {tags}
- User's stated interests: {interests}

WRITE a single pitch line.

Rules:
- ≤15 words.
- Lead with the concrete claim or the surprise, not the topic.
- Use active verbs ("argues", "maps", "shows", "debunks") not "discusses" or "explores".
- No marketing words ("game-changing", "must-read", "fascinating").
- No emoji.
- If the article doesn't match the user's interests, still write an honest pitch — don't oversell.

GOOD examples:
- "A neuroscientist argues your morning anxiety starts in your liver, not your brain."
- "Maps every container ship lost at sea in 2023; the pattern surprised me."
- "Why TypeScript's `satisfies` operator quietly replaced half your type assertions."

BAD examples:
- "An interesting look at the future of AI." (vague, no claim)
- "This article discusses productivity techniques." (banned phrase)
- "Must-read piece on climate change!" (marketing, no specifics)

Return JSON only:
{"pitch": "..."}
```

### 8.3 `prompts/score_components.md`

```
You are scoring an article for a personal reading queue. Return JSON only.

USER INTERESTS:
{interests_yaml}

ARTICLE:
- Title: {title}
- Tldr: {tldr}
- Summary: {summary}
- Tags: {tags}
- Word count: {word_count}
- Read minutes: {read_minutes}
- Published: {published_at}
- Days since published: {days_old}

USER'S RECENT READING (last 20 kept items, for novelty comparison):
{recent_kept_titles}

Score each component 0–10. Be honest; most articles are mediocre.

Return JSON only:
{
  "topic_match": {"score": 0-10, "reason": "≤20 words"},
  "recency_value": {"score": 0-10, "reason": "is this time-sensitive or evergreen?"},
  "effort_payoff": {"score": 0-10, "reason": "is the length justified?"},
  "surprise": {"score": 0-10, "reason": "does this challenge the user's usual reading?"}
}

Note: novelty and source_reputation are computed separately. Don't score them.
```

### 8.4 Prompt evaluation

Maintain `evals/golden.jsonl` — 30 hand-curated `(url, expected_score_bucket, expected_pitch_quality_notes)` triples. A `make eval` command runs current prompts against the golden set and reports drift. Run before any prompt edit ships.

-----

## 9. Pydantic schemas (`schemas.py`)

```python
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal

class ExtractedPage(BaseModel):
    title: str
    author: str | None = None
    published_at: str | None = None
    text: str
    word_count: int
    paywalled: bool = False

class SummarizeOutput(BaseModel):
    tldr: str = Field(max_length=300)
    summary: str = Field(max_length=2000)
    tags: list[str] = Field(min_length=1, max_length=6)

class PitchOutput(BaseModel):
    pitch: str = Field(max_length=150)

class ComponentScore(BaseModel):
    score: int = Field(ge=0, le=10)
    reason: str = Field(max_length=200)

class ScoreOutput(BaseModel):
    topic_match: ComponentScore
    recency_value: ComponentScore
    effort_payoff: ComponentScore
    surprise: ComponentScore
```

Every LLM call returns one of these via `response_model=...` in the wrapper. No `dict[str, Any]` ever crosses a module boundary.

-----

## 10. CLI surface (`cli.py`)

Built with `typer`. Commands:

```
rq add <url>                  # add a single URL
rq add-batch <file>           # newline-delimited URLs
rq list [--status queued]     # show queue
rq show <id|url>              # full record
rq find "<query>"             # full-text + embedding search
rq score [--all|--id N]       # rescore items
rq digest [--dry-run]         # generate (and send) weekly digest
rq kill <id>                  # mark killed
rq keep <id>                  # mark kept
rq read <id>                  # mark read
rq stats                      # queue health: size, age distribution, kill rate
rq export [--format json]     # full dump
rq import <file>              # backfill from Pocket/Instapaper export
rq doctor                     # check config, secrets, DB, model access
rq eval                       # run prompts against golden.jsonl
```

`rq doctor` is non-negotiable. Run it first when anything’s weird.

-----

## 11. Telegram bot surface (`bot.py`)

**Commands:** `/start`, `/add <url>`, `/queue`, `/stats`, `/digest_now`, `/kill_old`, `/help`.

**Inline behavior:** any message containing a URL is treated as `/add`. Bot replies with the pitch + `[open] [snooze] [kill]` buttons.

**Buttons** (callback_data is `action:item_id`):

- `open` — sends URL link, marks `opened` event.
- `snooze` — moves to `kept`, won’t appear in digest for 30 days.
- `kill` — marks `killed`, confirms with “🗑️ killed.”
- `mark_read` — marks `read`.

**Security:** bot only responds to `TELEGRAM_ALLOWED_USER_IDS` from env. Reject all others silently.

-----

## 12. Configuration (`config.py`)

`.env`:

```
ANTHROPIC_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789
DB_PATH=./rq.db
DIGEST_CRON="0 9 * * SUN"
LOCAL_TZ=America/Los_Angeles
LOG_LEVEL=INFO
```

`interests.yaml` (editable, hot-reloaded):

```yaml
active:
  - llm evals and benchmarks
  - urban planning and housing policy
  - long-form narrative journalism
  - systems programming (rust, zig)
  - cognitive science of attention
avoid:
  - crypto price commentary
  - generic productivity advice
  - vc twitter drama
goals_this_quarter:
  - prep for the talk on agentic eval design
  - decide if we should move to Tokyo
```

The `goals_this_quarter` block is part of the scoring prompt. Goals change what’s relevant *right now* in a way pure tags can’t capture.

-----

## 13. Failure modes & retries

|Failure                       |Detection             |Response                                                                          |
|------------------------------|----------------------|----------------------------------------------------------------------------------|
|LLM returns non-JSON          |Pydantic parse error  |1 retry with stricter nudge, then hard fail; row stays `queued` with `error` event|
|LLM rate limit (429)          |SDK exception         |Exponential backoff: 2s, 8s, 30s; max 3 tries                                     |
|LLM 5xx                       |SDK exception         |Same backoff                                                                      |
|Page fetch timeout            |httpx.TimeoutException|Fall back to Playwright; if that times out, store URL with `needs_review`         |
|Page fetch 403/401            |HTTP status           |Mark `paywalled=True`, write pitch from title alone                               |
|Playwright not installed      |ImportError           |Log warning at startup, skip fallback (don’t crash)                               |
|Embedding model not downloaded|Missing file          |Download on first run; show progress                                              |
|Telegram unreachable          |NetworkError          |Queue digest, retry every 10 min for up to 6 hours                                |
|Duplicate URL                 |Unique constraint     |Return existing item, increment `seen_count`                                      |
|DB locked                     |SQLite error          |Retry with jitter (SQLite + WAL handles this well)                                |

**Every failure writes an event.** No silent drops.

-----

## 14. Testing strategy

- **Unit:** scoring math, URL normalization, schema validation. Aim for 90% coverage on `score.py` and `ingest.py`.
- **Integration:** `vcr.py` cassettes for httpx and Anthropic SDK. CI replays them; no live calls.
- **Eval:** `evals/golden.jsonl` — 30 URLs you’ve personally read and rated. After every prompt change, run `rq eval` and verify score correlation > 0.7 with your ratings, and that pitch quality (manually reviewed) hasn’t regressed.
- **Smoke:** `rq doctor` on every deploy.

-----

## 15. Build plan (day by day)

|Day|Output                                                                                                  |Definition of done                                                  |
|---|--------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
|1  |Repo skeleton, SQLite migrations, config, logging, `rq doctor`, `rq add` end-to-end with stub enrichment|`rq add https://...` stores a row with raw text                     |
|2  |Real enrichment (all 3 LLM passes), Pydantic schemas, LLM wrapper with retries, embedding               |`rq show <id>` shows pitch, summary, tags, score, breakdown         |
|3  |Scoring math, domain stats, novelty calc, `rq score --all`, golden eval harness                         |`rq eval` runs and prints correlation report                        |
|4  |Telegram bot: ingest, buttons, allowed-users gate                                                       |Add URL via phone, get pitch back, tap kill, see row update         |
|5  |Digest composer, scheduler, “kill these” selection logic                                                |`rq digest --dry-run` produces a good-looking message; cron sends it|
|6  |Feedback loop, interest-drift suggestions, Pocket/Instapaper import, `rq stats`                         |Backfill 200 historical bookmarks, digest reflects domain reputation|
|7  |Polish: pitch prompt iteration (this is where you’ll spend the time), error UX in bot, deploy to Fly.io |First real weekly digest sent to yourself                           |

-----

## 16. Deferred (v2+)

- Web UI for browsing history
- iOS Shortcut as alternative ingest (instead of Telegram)
- Multiple users
- Highlights / annotations
- Audio TTS of summaries for commute
- Group reading queues with friends
- Auto-detect when you’re in “deep work” mode and pause notifications

Resist all of these until v1 has been your daily driver for 30 days.

-----

## 17. Repo layout

```
reading-queue/
├── README.md
├── SPEC.md                  ← this file
├── pyproject.toml
├── .env.example
├── interests.yaml
├── rq.db                    ← gitignored
├── prompts/
│   ├── summarize.md
│   ├── pitch.md
│   └── score_components.md
├── migrations/
│   └── 001_init.sql
├── src/rq/
│   ├── __init__.py
│   ├── cli.py
│   ├── bot.py
│   ├── scheduler.py
│   ├── config.py
│   ├── db.py
│   ├── schemas.py
│   ├── llm.py               ← the one wrapper
│   ├── fetch.py
│   ├── ingest.py
│   ├── enrich.py
│   ├── score.py
│   ├── digest.py
│   ├── learn.py
│   └── logging.py
├── tests/
│   ├── cassettes/
│   ├── test_score.py
│   ├── test_ingest.py
│   └── test_schemas.py
└── evals/
    ├── golden.jsonl
    └── run.py
```

-----

## 18. Operational notes

- **Backup:** nightly `sqlite3 rq.db .dump > backup/$(date).sql` rotated weekly.
- **Cost:** ~$0.50/month at 20 URLs/day with Haiku for bulk + Sonnet for pitch/score. Set a hard monthly cap in `config.py` and refuse new enrichments if exceeded (queue them).
- **Privacy:** raw_text never leaves your machine except to Anthropic’s API. No analytics, no third parties.

-----