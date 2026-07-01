#!/usr/bin/env bash
# Quick health/status triage for the Family Assistant stack (cloud VPS).
#
# One-shot snapshot: current commit, container status, app /health, applied
# migration, disk headroom, and the tail of the app log. Read-only — safe to
# run any time. (Cloud replacement for the old GPU-era `fa-doctor`.)
#
#   ./scripts/doctor.sh
set -uo pipefail   # deliberately not -e: run every check even if one fails

REPO="${REPO:-$HOME/family-assistant}"
cd "$REPO"
export COMPOSE_FILE="${COMPOSE_FILE:-compose.cloud.yml}"

echo "== commit =="
git log --oneline -1

echo
echo "== containers =="
docker compose ps

echo
echo "== app /health =="
docker compose exec -T app python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health',timeout=5).read().decode())" \
  2>&1 || echo "health check FAILED"

echo
echo "== migration (alembic current) =="
docker compose exec -T app alembic current 2>&1 || true

echo
echo "== disk =="
df -h / | tail -1

echo
echo "== recent app logs =="
docker compose logs --tail=25 app
