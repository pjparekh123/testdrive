-- 001_init.sql — initial schema for the Smart Reading Queue.
-- Matches SPEC §6 exactly. Migration policy: append-only. Never edit a
-- committed migration; add a new numbered file instead.

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
