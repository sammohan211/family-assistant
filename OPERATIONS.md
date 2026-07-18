# Operations

Day-to-day running of the stack on the cloud VPS. First-time install: `SETUP.md`. Using the app: `USER_GUIDE.md`. The retired home-GPU/Ollama procedures are in git history (`git log -- OPERATIONS.md`).

On the box, work from `~/family-assistant` with `export COMPOSE_FILE=compose.cloud.yml` in `~/.bashrc` — then plain `docker compose ...` targets this stack. **Gotcha:** the VM's global `COMPOSE_FILE` may point at another tenant's repo (see PRD §17.10) — when in doubt, pass `-f compose.cloud.yml` explicitly.

## Quick reference

```bash
./scripts/deploy.sh                  # safe one-command deploy (pull, backup, build, migrate, health-check, rollback-on-fail)
./scripts/doctor.sh                  # read-only status snapshot (commit, containers, /health, alembic current, disk, logs)
./scripts/rollback.sh [commit]       # roll code back (default HEAD~1) and rebuild
docker compose ps                    # service status
docker compose logs -f app           # tail a service (also: caddy, postgres)
docker compose down                  # stop all; data preserved in volumes
docker compose up -d --build         # rebuild + start
docker compose exec app bash         # shell in the app container
docker compose exec postgres psql -U family_assistant
docker compose exec app pytest       # test suite
```

## Deploy

```bash
./scripts/deploy.sh
```

Fast-forwards to `origin/main`, dumps the DB *before* migrating, rebuilds, waits for the compose healthcheck, migrates, verifies `/health`. On any failure it resets to the starting commit, rebuilds, and exits non-zero. Options: `HEALTH_TIMEOUT=<secs>` (default 120), `BRANCH=<name>`.

**Rollback reverts code, not schema.** If a migration is the culprit, restore the pre-migrate dump (below) instead of relying on `rollback.sh`.

The manual equivalent: `git pull` → `docker compose up -d --build` → `docker compose exec app alembic upgrade head` → check logs. `up -d --build` is idempotent; `alembic upgrade head` with nothing pending is a no-op.

## Logs & debugging

```bash
docker compose logs -f app           # live; --tail=200 / --since=10m for slices
```

- `app` — tracebacks, request lines, gateway errors.
- `caddy` — TLS, upstream errors (browser can't reach the app at all).

For "why did the assistant do *that*?": each call writes one `assistant_interactions` row plus per-stage `interaction_traces` rows (input → context → llm → validation → risk → decision → execution → persist). Also browsable in-app at `/assistant/interactions/{id}/trace`.

```bash
# Recent interactions
docker compose exec postgres psql -U family_assistant -c \
  "SELECT id, created_at, input_text, reply FROM assistant_interactions ORDER BY id DESC LIMIT 10;"
# Full trace for one (substitute the id)
docker compose exec postgres psql -U family_assistant -c \
  "SELECT ts_ms, stage, event, payload FROM interaction_traces WHERE interaction_id = 42 ORDER BY ts_ms;"
```

## Migrations

```bash
docker compose exec app alembic upgrade head   # apply pending
docker compose exec app alembic current        # what's applied
docker compose exec app alembic downgrade -1   # rollback one (careful)
```

## Backups

**Automated daily (the safety net):** `scripts/db-backup.sh`, deployed to `/root/db-backup.sh` (re-copy after a `git pull` if it changed: `cp ~/family-assistant/scripts/db-backup.sh /root/db-backup.sh && chmod +x /root/db-backup.sh`). Cron runs it daily at 03:00:

```
0 3 * * * /root/db-backup.sh >> /root/backups/backup.log 2>&1
```

It does `pg_dump | gzip` into `/root/backups/`, keeps the newest 14, and refuses to promote or rotate on a dump smaller than `MIN_BYTES` (default 5K; healthy ≈ 17K) — so a truncated dump can't rotate out good ones. Check `backup.log` for one `backup OK:` line per day.

**Manual dump / restore:**

```bash
docker compose exec -T postgres pg_dump -U family_assistant family_assistant | gzip > /root/backups/manual_$(date +%Y%m%d_%H%M).sql.gz
gunzip -c <dump>.sql.gz | docker compose exec -T postgres psql -U family_assistant family_assistant
```

Restore into an *empty* DB: `docker compose down -v` → `up -d` → restore → then migrations. Rehearse safely with a throwaway DB (`createdb restore_test` → restore there → check counts → `dropdb restore_test`).

**Off-box copy:** dumps live on the VPS disk, so they don't survive losing the whole server. Occasionally, from the laptop:

```bash
rsync -avz root@<vps>:/root/backups/ ~/family-backups/
```

Plus an occasional Hetzner snapshot (console or `hcloud server create-image --type snapshot`) as a whole-server net.

## Users

```bash
docker compose exec app python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('new-password'))"
```

Paste into `.env` as `USERn_PASSWORD_HASH` (**double every `$` to `$$`** — Compose interpolation), set `USERn_EMAIL` / `USERn_NAME`, then `docker compose up -d app`. Users re-seed from `.env` at startup.

> **`up -d`, not `restart`** — `restart` reuses the old environment and silently ignores `.env` changes. Applies to every `.env` edit.

The code supports `USER1_*` and `USER2_*` only; more requires extending `settings.py` and `auth/services.py:_seed_initial_users`.

## LLM (OpenRouter)

The model is `OPENROUTER_MODEL` in `.env`; change it → `docker compose up -d app`. Pick a cheap, currently-listed model that's reliable at JSON `response_format`, ideally with a no-retention policy (browse https://openrouter.ai/models).

- **404 from `/chat/completions`** — the model snapshot was retired by the provider; pick a listed one.
- **401** — bad/expired `OPENROUTER_API_KEY`.
- Assistant errors surface in `docker compose logs app` and in the interaction's `error_log` / trace.

## Common issues

- **App keeps restarting after a config change** — `docker compose logs --tail=50 app`; almost always `.env` (password mismatch, missing value, unescaped `$`).
- **Assistant submits but nothing happens** — check `app` logs for a traceback, then the interaction trace; then the OpenRouter items above.
- **`alembic upgrade head`: "Can't locate revision..."** — the DB is ahead of the code (repo was downgraded). Re-pull newer code, or `alembic downgrade` to match.
- **Disk filling** — `docker system prune` (removes only unused images/cache); check `/root/backups` rotation; `df -h`.
- **Caddy site changes not taking effect** — see PRD §17.10 (validate + reload; single-file bind-mount inode gotcha).

## Reference: layout

```
~/family-assistant/
├── .env                  # secrets, not in git
├── compose.cloud.yml     # app + postgres + caddy
├── Caddyfile             # this app's site + `import sites/*.caddy` (multi-tenant edge, PRD §17.10)
├── sites/                # tenant site blocks (untracked; README explains)
├── alembic/versions/     # migrations
├── scripts/              # deploy.sh, doctor.sh, rollback.sh, db-backup.sh, seed_*.py
├── src/family_assistant/ # app code
└── tests/
```

Volumes: `postgres_data` (the database), `caddy_data`/`caddy_config` (certs, Caddy state). `/root/backups/` and `/root/static/` (static tenants) live on the host.
