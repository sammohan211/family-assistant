#!/usr/bin/env bash
# Off-box copy of Family Assistant backups — run on the LAPTOP, not the VPS.
#
# Pulls every DB dump from the VPS (/root/backups/) into a local folder, plus a
# dated snapshot of the config a rebuild needs (.env, Caddyfile, sites/).
# Never deletes local files, so the laptop keeps history the VPS has rotated out.
#
#   ./scripts/pull-backups.sh           # pull what's there
#   ./scripts/pull-backups.sh --fresh   # take a new dump on the VPS first
set -euo pipefail

VPS="${VPS:-family-assistant}"                  # ssh host alias (see ~/.ssh/config)
REMOTE_REPO="${REMOTE_REPO:-/root/family-assistant}"
REMOTE_BACKUPS="${REMOTE_BACKUPS:-/root/backups}"
DEST="${DEST:-$HOME/family-backups}"

if [ "${1:-}" = "--fresh" ]; then
  echo "== Taking a fresh dump on $VPS"
  ssh "$VPS" "/root/db-backup.sh 2>&1 | tee -a $REMOTE_BACKUPS/backup.log"
fi

echo "== Pulling dumps -> $DEST"
mkdir -p "$DEST"
rsync -az --stats "$VPS:$REMOTE_BACKUPS/" "$DEST/" | grep -E 'files transferred|Total transferred'

# Verify the newest dump survived the trip (gzip integrity + has tables).
NEWEST=$(ls -1t "$DEST"/family_assistant_*.sql.gz | head -1)
TABLES=$(gunzip -c "$NEWEST" | grep -c '^CREATE TABLE' || true)
if [ "$TABLES" -lt 1 ]; then
  echo "FAILED: newest dump $NEWEST has no CREATE TABLE statements" >&2
  exit 1
fi
echo "   newest: $(basename "$NEWEST") ($(du -h "$NEWEST" | cut -f1), $TABLES tables)"

# Config snapshot — .env holds secrets, so keep it owner-only.
CONF="$DEST/config/$(date +%Y%m%d)"
echo "== Pulling config -> $CONF"
mkdir -p "$CONF"
chmod 700 "$DEST/config"
rsync -a "$VPS:$REMOTE_REPO/.env" "$VPS:$REMOTE_REPO/Caddyfile" "$VPS:$REMOTE_REPO/sites" "$CONF/"
chmod 600 "$CONF/.env"

echo "== Done: $(ls -1 "$DEST"/*.sql.gz | wc -l) dumps in $DEST"
