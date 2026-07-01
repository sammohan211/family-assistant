#!/usr/bin/env bash
# Manual rollback for Family Assistant (cloud VPS).
#
# For when a deploy landed cleanly but the app misbehaves. Resets the checkout
# to an earlier commit and rebuilds. Defaults to the previous commit (HEAD~1);
# pass a commit/tag to target a specific one.
#
# DB note: this reverts *code*, not schema. Migrations are not auto-downgraded.
# If a migration needs reverting, restore a dump from ~/backups (OPERATIONS.md)
# or run `docker compose exec app alembic downgrade <rev>` deliberately.
#
#   ./scripts/rollback.sh            # back to HEAD~1
#   ./scripts/rollback.sh <commit>   # back to a specific commit/tag
set -euo pipefail

REPO="${REPO:-$HOME/family-assistant}"
TARGET="${1:-HEAD~1}"

cd "$REPO"
export COMPOSE_FILE="${COMPOSE_FILE:-compose.cloud.yml}"

log() { echo "$(date '+%F %T') rollback: $*"; }

RESOLVED=$(git rev-parse --verify "$TARGET")
log "resetting $(git rev-parse --short HEAD) -> ${RESOLVED:0:8} ($TARGET)"
git reset --hard "$RESOLVED"

log "rebuilding + restarting"
docker compose up -d --build

log "done. If a migration needs reverting, restore from ~/backups or downgrade alembic manually."
docker compose ps
