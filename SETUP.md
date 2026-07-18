# Family Assistant Setup

Deploying the stack (app + Postgres + Caddy, `compose.cloud.yml`) to a cloud VPS, with chat via OpenRouter. This is the only supported deployment; the retired home-GPU/Ollama path is in git history (`git log -- SETUP.md`).

## 1. Provision the VPS

Any small Linux VPS (currently Hetzner). Install Docker, then:

```bash
git clone <repo url> family-assistant && cd family-assistant
```

Point your domain's A record at the VPS **before** first start, so Caddy can complete the ACME challenge on ports 80/443. (With DuckDNS, subdomains resolve automatically.)

## 2. Build `.env`

```bash
cp .env.example .env
```

Fill in (generators in the comments of `.env.example`):

- `POSTGRES_PASSWORD` — random string; use the same value inside `DATABASE_URL`.
- `SESSION_SECRET` — `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY` (from https://openrouter.ai/keys), `OPENROUTER_MODEL` — any JSON-capable, currently-listed model (see `.env.example` for the current pick).
- `APP_HOSTNAME` / `APP_BASE_URL` — your public domain.
- `CADDY_TLS=you@email.com` — a real email gets a Let's Encrypt cert (`internal` is for LAN-only experiments).
- `USER1_*` / `USER2_*` — can stay blank until step 5.
- `USE_MOCK_LLM=false` (`true` swaps in the offline keyword mock from `ai_gateway/llm_mock.py` — dev only).

## 3. Bring the stack up

```bash
export COMPOSE_FILE=compose.cloud.yml   # put in ~/.bashrc; see OPERATIONS.md
docker compose up -d --build
docker compose exec app alembic upgrade head
docker compose ps                        # postgres healthy, app healthy, caddy up
```

If `app` errors on first start it's almost always a `.env` typo — check `DATABASE_URL` matches `POSTGRES_PASSWORD`.

For running pytest on the box (optional): `docker compose exec postgres createdb -U family_assistant family_assistant_test`.

## 4. Verify

`curl https://<your-domain>/health` — or from inside the box, bypassing Caddy:

```bash
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"
```

## 5. Create login credentials

```bash
docker compose exec app python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your-password'))"
```

Paste the hash into `.env` as `USER1_PASSWORD_HASH`, **with every `$` doubled to `$$`** — Compose treats a single `$` as a variable reference and silently blanks parts of the hash (`WARN ... variable is not set` in the logs is the tell). Fill `USER1_EMAIL` / `USER1_NAME`, then:

```bash
docker compose up -d app     # NOT `restart` — restart doesn't re-read .env
```

Sign in with the plaintext password, then send one assistant command to confirm the OpenRouter round-trip.

## 6. Ongoing

- Day-to-day (deploys, logs, backups, users): `OPERATIONS.md`.
- The VM's Caddy also serves other sites (multi-tenant edge): `PRD_AND_ROADMAP.md` §17.10.
- Using the app: `USER_GUIDE.md`.
