#!/usr/bin/env bash
# Daily Postgres backup for Family Assistant.
#
# Runs on the VPS (deployed to /root/db-backup.sh, fired by cron at 03:00).
# Dumps the DB, gzips it, and only promotes the file if it passes a size
# sanity check, so a truncated/empty dump can never overwrite or rotate out a
# good one. The off-box copy is handled separately by an rsync cron on the
# home desktop (see OPERATIONS.md "Off-box safety").
set -euo pipefail

REPO="${REPO:-$HOME/family-assistant}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${KEEP:-14}"               # keep the newest N dumps
MIN_BYTES="${MIN_BYTES:-5000}"   # reject a dump smaller than this (a healthy dump is ~17K)

cd "$REPO"
export COMPOSE_FILE="${COMPOSE_FILE:-compose.cloud.yml}"
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%Y%m%d_%H%M)
OUT="$BACKUP_DIR/family_assistant_${STAMP}.sql.gz"

# Dump to a temp file first; pipefail makes a pg_dump failure abort before promotion.
docker compose exec -T postgres pg_dump -U family_assistant family_assistant \
  | gzip > "$OUT.tmp"

# Size sanity gate: a real dump is ~17K gzipped. If it's tiny, something went
# wrong (empty DB, partial dump, auth change) — bail without promoting or
# rotating, so the existing good dumps are left untouched.
SIZE=$(stat -c%s "$OUT.tmp")
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
  rm -f "$OUT.tmp"
  echo "$(date '+%F %T') backup FAILED: dump only ${SIZE}B (< ${MIN_BYTES}B), not promoted" >&2
  exit 1
fi

# Promote only on success (a failed dump never replaces a good one).
mv "$OUT.tmp" "$OUT"

# Rotation: delete all but the newest $KEEP dumps.
ls -1t "$BACKUP_DIR"/family_assistant_*.sql.gz 2>/dev/null \
  | tail -n +$((KEEP+1)) | xargs -r rm -- || true

echo "$(date '+%F %T') backup OK: $OUT ($(du -h "$OUT" | cut -f1))"
