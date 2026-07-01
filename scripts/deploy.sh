#!/usr/bin/env bash
# One-command deploy for Family Assistant (cloud VPS).
#
# Runs on the box from the repo dir. Fast-forwards to the latest origin/main,
# backs up the DB, rebuilds the app image, waits for the container to report
# healthy, applies migrations, and verifies /health. If any step fails it rolls
# the checkout back to the commit it started from, rebuilds, and exits non-zero
# — so a broken deploy doesn't linger.
#
# DB note: a rollback reverts *code*, not schema. Migrations are not
# auto-downgraded; if a migration itself is the problem, restore the pre-deploy
# dump from ~/backups (see OPERATIONS.md "Database").
#
#   ./scripts/deploy.sh            # deploy origin/main
#   BRANCH=foo ./scripts/deploy.sh # deploy a different branch
set -euo pipefail

REPO="${REPO:-$HOME/family-assistant}"
BRANCH="${BRANCH:-main}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"   # seconds to wait for the app to go healthy

cd "$REPO"
export COMPOSE_FILE="${COMPOSE_FILE:-compose.cloud.yml}"

log() { echo "$(date '+%F %T') deploy: $*"; }

# Remember where we started, so we can put it back if anything fails.
PREV_COMMIT=$(git rev-parse HEAD)

rollback() {
  log "FAILED — rolling back code to ${PREV_COMMIT:0:8}"
  git reset --hard "$PREV_COMMIT"
  docker compose up -d --build || true
  log "rolled back. If a migration ran, restore from ~/backups (see OPERATIONS.md)."
  exit 1
}
trap rollback ERR

# 1. Fast-forward the checkout to the remote branch tip.
log "fetching origin/$BRANCH"
git fetch --prune origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW_COMMIT=$(git rev-parse HEAD)
log "deploying ${PREV_COMMIT:0:8} -> ${NEW_COMMIT:0:8}"

# 2. Back up the DB *before* migrating, so a bad migration is recoverable.
if [ -x "$REPO/scripts/db-backup.sh" ]; then
  log "backing up DB"
  "$REPO/scripts/db-backup.sh"
else
  log "WARN: scripts/db-backup.sh not executable — skipping pre-deploy backup"
fi

# 3. Rebuild + (re)start. Idempotent: only changed containers are recreated.
log "building + starting containers"
docker compose up -d --build

# 4. Wait for the app's compose healthcheck to report healthy.
log "waiting for app health (timeout ${HEALTH_TIMEOUT}s)"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while true; do
  health=$(docker compose ps app --format '{{.Health}}' 2>/dev/null || true)
  [ "$health" = "healthy" ] && { log "app healthy"; break; }
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "app not healthy after ${HEALTH_TIMEOUT}s (last state: '${health:-unknown}')"
    docker compose logs --tail=40 app || true
    false   # trip the ERR trap -> rollback
  fi
  sleep 3
done

# 5. Apply any pending migrations (no-op when nothing is pending).
log "applying migrations"
docker compose exec -T app alembic upgrade head

# 6. Verify the app answers /health from inside the container.
log "verifying /health"
docker compose exec -T app python -c \
  "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://localhost:8000/health',timeout=5).read() else 1)"

trap - ERR
log "OK: deployed ${NEW_COMMIT:0:8}"
docker compose ps
docker compose logs --tail=20 app
