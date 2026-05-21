# Operations

Day-to-day running of the Family Assistant stack on the Omarchy desktop. For first-time install, see `SETUP.md`. For using the app's features (grocery, meal plan, assistant, etc.), see `USER_GUIDE.md`.

All commands run from `~/Projects/family_assistant` on the desktop (over SSH from the laptop, or directly).

---

## Save typing: set COMPOSE_FILE

Most operational commands (`ps`, `logs`, `exec`, `restart`, `down`) work without `-f` flags because Compose finds the running project by directory name. Only `up` and `build` need both compose files merged so GPU config is included. Make that the default by exporting `COMPOSE_FILE` in your shell rc (`~/.bashrc` on Arch):

```bash
export COMPOSE_FILE=compose.yml:compose.gpu.yml
```

After `source ~/.bashrc`, plain `docker compose up -d --build` picks up both files. The rest of this doc assumes that.

For everyday use, source `scripts/family.sh` instead — it exports `COMPOSE_FILE` for you and adds `fa-up` (bring everything up, wait for health, run migrations, warm the model, doctor), `fa-down` (stop containers, preserve volumes), `fa-status`, `fa-logs <svc>`, `fa-ops`, `fa-warm`, `fa-restart`, `fa-rebuild`, and `fa-doctor`:

```bash
echo 'source ~/Projects/family_assistant/scripts/family.sh' >> ~/.bashrc
source ~/.bashrc
fa-doctor   # one-shot: compose ps + ollama ps + GPU memory + last 20 app log lines
```

This doc remains the source of truth for what each underlying command does.

---

## Quick reference

```bash
docker compose ps                              # service status
docker compose logs -f app                     # tail one service
docker compose logs -f app ollama caddy        # tail multiple
docker compose restart app                     # restart one service
docker compose down                            # stop all (data preserved in volumes)
docker compose up -d                           # start all
docker compose up -d --build                   # rebuild app image, then start
docker compose exec app bash                   # shell inside the app container
docker compose exec postgres psql -U family_assistant
docker compose exec ollama ollama list
docker compose exec app pytest                 # run the test suite
```

---

## Cold start: both machines were off

If desktop and laptop have both been shut down (power outage, away for a while, deliberate shutdown):

1. **Power on the desktop.** Let it finish booting (~30 s).
2. **Wait ~1 minute, do nothing.** Docker starts on boot via systemd, then brings every service back up because of `restart: unless-stopped` in `compose.yml`. You don't need to SSH in or run any commands.
3. **Power on the laptop.** Tailscale reconnects automatically on most Linux setups (it's a systemd service — `sudo systemctl enable tailscaled` once, stays on across reboots).
4. **Open the app URL in the browser** — whatever you set as `APP_BASE_URL` (e.g. `https://omarchy.tail38845d.ts.net`).

The **first request** after a cold start takes ~20–40 s while Ollama loads the model into VRAM. After that it's fast.

**If the page doesn't load after ~2 minutes**, SSH into the desktop (`ssh sam@omarchy.tail38845d.ts.net`) and triage:

```bash
docker compose ps                              # everything should be Up or Up (healthy)
sudo systemctl status docker                   # Docker itself running?
sudo tailscale status                          # tailnet up on the desktop?
```

- A service stuck in `Restarting`: `docker compose logs --tail=50 <service>` (most likely `app` — usually a `.env` problem).
- Docker not running: `sudo systemctl start docker`.
- Can't SSH at all: Tailscale is down on the desktop. Hook up keyboard + monitor, `sudo tailscale up`.

---

## Update the app after a `git pull`

The flow whenever you pull new code:

```bash
git pull
docker compose up -d --build                   # rebuild image, recreate changed containers
docker compose exec app alembic upgrade head   # apply any new migrations
docker compose logs --tail=30 app              # sanity check it came up cleanly
```

`up -d --build` is idempotent — Compose only recreates containers whose images or env actually changed. Everything else keeps running.

Skip the `alembic upgrade head` if you know the commit didn't touch `alembic/versions/`. Running it when nothing's pending is a no-op anyway, so when in doubt, run it.

---

## Logs & debugging

```bash
docker compose logs -f app                     # follow live
docker compose logs --tail=200 app             # last 200 lines, no follow
docker compose logs --since=10m app            # last 10 minutes
docker compose logs app ollama                 # multiple services interleaved
```

`Ctrl+C` exits the follow without stopping the container.

When the assistant looks broken, the three useful tails:
- `app` — Python tracebacks, request lines, gateway errors.
- `ollama` — model loading, token generation.
- `caddy` — TLS handshakes, upstream errors (if the browser can't reach the app at all).

For "why did the assistant do *that*?" — check the `interaction_traces` table (see the Database section below). Each assistant call writes one row per pipeline stage (input → context → llm → validation → risk → decision → execution → persist) so a single query reconstructs the full lifecycle without re-running anything.

---

## Database

**Shell in:**
```bash
docker compose exec postgres psql -U family_assistant
```

**Useful one-liners** (run without entering psql):
```bash
# Most recent assistant interactions
docker compose exec postgres psql -U family_assistant -c \
  "SELECT id, created_at, input_text, reply FROM assistant_interactions ORDER BY id DESC LIMIT 10;"

# Full pipeline trace for one interaction (substitute the id)
docker compose exec postgres psql -U family_assistant -c \
  "SELECT ts_ms, stage, event, payload FROM interaction_traces WHERE interaction_id = 42 ORDER BY ts_ms;"

# Row counts per table
docker compose exec postgres psql -U family_assistant -c \
  "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"
```

**Migrations:**
```bash
docker compose exec app alembic upgrade head           # apply pending
docker compose exec app alembic current                # what's applied
docker compose exec app alembic history --verbose      # full chain
docker compose exec app alembic downgrade -1           # rollback one (careful)
```

**Backup** (dump to a file on the desktop):
```bash
docker compose exec -T postgres pg_dump -U family_assistant family_assistant \
  | gzip > ~/backups/family_assistant_$(date +%Y%m%d_%H%M).sql.gz
```

Create `~/backups` first. The `-T` disables TTY so the pipe works. Run weekly or before any risky change.

**Restore from a backup:**
```bash
gunzip -c ~/backups/family_assistant_YYYYMMDD_HHMM.sql.gz \
  | docker compose exec -T postgres psql -U family_assistant family_assistant
```

(Restore into an empty DB. If you're recovering, `docker compose down -v` first to drop the existing volume, then `up -d`, then restore *before* running new migrations.)

---

## Users

Add a new user (or reset a password):

```bash
docker compose exec app python -c \
  "from argon2 import PasswordHasher; print(PasswordHasher().hash('new-password'))"
```

Paste the hash into `.env` as `USERn_PASSWORD_HASH`, **doubling every `$` to `$$`** (Compose interpolation — see `.env.example`). Set `USERn_EMAIL` and `USERn_NAME` alongside.

```bash
docker compose restart app
```

The app re-seeds users from `.env` at startup — the new credentials are now active.

(The code currently supports `USER1_*` and `USER2_*`. For more, extend `settings.py` and `auth/services.py:_seed_initial_users`.)

---

## LLM models

**List installed:**
```bash
docker compose exec ollama ollama list
```

**Pull a new one:**
```bash
docker compose exec ollama ollama pull <model-tag>     # e.g. llama3.1:70b-instruct-q4_K_M
```

The 3090 has 24 GB VRAM, so anything up to a ~30 B parameter Q4-quantized model fits comfortably.

**Switch which model the app uses:**

Edit `.env` → `OLLAMA_MODEL=<new-tag>` → `docker compose restart app`. Ollama keeps the previous one in its volume; pull it again is free.

**Delete an unused model** (reclaim disk):
```bash
docker compose exec ollama ollama rm <model-tag>
```

---

## Stopping & starting

**Stop overnight or while traveling:**
```bash
docker compose down                            # stops + removes containers; volumes preserved
```

Data (`postgres_data`, `ollama_data`, `caddy_data`) persists across `down`. Next `up -d` resumes where you left off — no re-pulling models, no losing rows.

**Dangerous version — wipes data too:**
```bash
docker compose down -v                         # also removes volumes — DB and models gone
```

Only use when you want a clean slate (development, after restoring from a backup).

**Auto-start on reboot:**

The compose services already have `restart: unless-stopped`, so once `up -d` has run, Docker brings them back automatically when the desktop reboots. No systemd unit needed.

---

## Common issues

**"name not resolved" hitting `family.local` or the tailnet hostname from the laptop**
- Tailscale dropped: `sudo tailscale status` on both ends. `sudo tailscale up` to reconnect.
- MagicDNS off: turn it back on in the Tailscale admin console.

**App keeps restarting after a config change**
```bash
docker compose logs --tail=50 app
```
99% of the time it's a `.env` mistake — `POSTGRES_PASSWORD` ≠ password in `DATABASE_URL`, missing required value, or a `$` in a hash that wasn't escaped to `$$`.

**Assistant submits but no reply appears**
- Check `docker compose logs app` for a traceback when the POST landed.
- Check `docker compose logs ollama` — if no activity, the app isn't reaching it.
- Verify model is pulled: `docker compose exec ollama ollama list` should show the tag in `OLLAMA_MODEL`.

**`alembic upgrade head` says "Can't locate revision identified by..."**
- Means the DB has a revision the code doesn't know about (you downgraded the repo). Either re-pull the newer code or `alembic downgrade <older-revision>` to match.

**Disk filling up**
- Old Ollama models eating space: `docker compose exec ollama ollama list` then `ollama rm` the ones you're not using.
- Old Docker images / build cache: `docker system prune` (safe — only removes unused).

---

## Reference: file layout

```
~/Projects/family_assistant/
├── .env                    # secrets, not in git
├── compose.yml             # base service definitions
├── compose.gpu.yml         # GPU overlay for ollama
├── Caddyfile               # reverse proxy config
├── Dockerfile              # app image build
├── alembic/versions/       # database migrations
├── src/family_assistant/   # app code
└── tests/                  # pytest suite

~/backups/                  # pg_dump output (create yourself)
```

Docker-managed volumes (not on disk paths you'd browse):
- `family_assistant_postgres_data` — the database
- `family_assistant_ollama_data` — pulled LLM models
- `family_assistant_caddy_data` / `_config` — Caddy state, internal CA
