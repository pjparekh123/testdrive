#!/usr/bin/env bash
# Nightly SQLite backup (§18). Dumps the DB to backup/ and rotates weekly.
#
#   DB_PATH=./rq.db ./scripts/backup.sh
#
# Cron (nightly at 03:00) — see README "Backups":
#   0 3 * * *  cd /path/to/reading-queue && DB_PATH=./rq.db ./scripts/backup.sh
set -euo pipefail

DB_PATH="${DB_PATH:-./rq.db}"
BACKUP_DIR="${BACKUP_DIR:-./backup}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if [ ! -f "$DB_PATH" ]; then
  echo "backup: no database at $DB_PATH — nothing to do" >&2
  exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/rq-$STAMP.sql"

# Logical dump (consistent under WAL). Prefer the sqlite3 CLI; fall back to
# Python's stdlib iterdump so no extra binary is required.
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".dump" > "$OUT"
else
  python3 - "$DB_PATH" > "$OUT" <<'PY'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
for line in con.iterdump():
    print(line)
PY
fi
gzip -f "$OUT"
echo "backup: wrote $OUT.gz"

# Rotate: delete dumps older than RETENTION_DAYS.
find "$BACKUP_DIR" -name 'rq-*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
echo "backup: rotated dumps older than ${RETENTION_DAYS}d"
