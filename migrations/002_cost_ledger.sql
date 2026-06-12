-- 002_cost_ledger.sql — persist monthly LLM spend for the §18 cost cap.
-- Append-only: never edit a committed migration; add a new numbered file.

CREATE TABLE cost_ledger (
  month     TEXT PRIMARY KEY,           -- 'YYYY-MM' (UTC)
  spent_usd REAL NOT NULL DEFAULT 0,
  updated_at TIMESTAMP
);

INSERT INTO schema_version VALUES (2);
