# Family Assistant

Household management web app with an embedded AI assistant. Personal project for one household.

See [`family_assistant_prd.md`](family_assistant_prd.md) for the full PRD (version 1.0 — ready to build).

## Stack

- **Backend**: FastAPI (Python 3.11+), SQLAlchemy 2.x, Alembic, Pydantic v2
- **Frontend**: Jinja2 + HTMX + Alpine.js + Tailwind CSS (server-rendered)
- **Database**: PostgreSQL 16 + pgvector
- **LLM runtime**: Ollama (sidecar container, OpenAI-compatible API)
- **Deployment**: Docker Compose, portable between a home GPU box and a rented cloud VM (see PRD Section 17)
- **Package manager**: [uv](https://docs.astral.sh/uv/)

## Local setup

Install `uv` once (if you don't have it):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then from the repo root:

```bash
uv sync --extra dev          # creates .venv, installs deps + dev tools, generates uv.lock
uv run pre-commit install    # activates pre-commit hooks (gitleaks, ruff, etc.)
cp .env.example .env         # fill in values; never commit a populated .env
```

Run commands inside the project env with `uv run <cmd>` (e.g., `uv run pytest`), or activate the env once with `source .venv/bin/activate`.

## Running the stack with Docker

The Docker Compose stack runs identically at home and in the cloud (PRD Section 17). Only `.env` and the choice of compose overrides differ.

**Home (with NVIDIA GPU):**

```bash
cp .env.example .env       # fill in POSTGRES_PASSWORD, SESSION_SECRET, etc.
docker compose -f compose.yml -f compose.gpu.yml up -d --build
docker compose exec ollama ollama pull llama3.1:8b         # one-time
docker compose exec ollama ollama pull nomic-embed-text    # one-time
```

**Cloud (CPU-only or any host without NVIDIA):**

```bash
cp .env.example .env       # set CADDY_TLS=you@email.com, APP_HOSTNAME=your.domain
docker compose up -d --build
docker compose exec ollama ollama pull llama3.2:3b         # smaller model for CPU
docker compose exec ollama ollama pull nomic-embed-text
```

Verify:

```bash
curl -k https://${APP_HOSTNAME}/health
# {"status":"ok"}
```

Caddy serves HTTPS on port 443 (internal CA at home, Let's Encrypt in cloud). Postgres and Ollama are only reachable from within the Compose network — never published to the host.

## First-run database setup

Once the stack is up, run migrations and seed users.

**1. Generate password hashes for the two adults** and paste them into `.env`:

```bash
uv run python -c "from argon2 import PasswordHasher; from getpass import getpass; print(PasswordHasher().hash(getpass('Password: ')))"
```

Set `USER1_EMAIL` / `USER1_PASSWORD_HASH` and `USER2_EMAIL` / `USER2_PASSWORD_HASH` in `.env`.

**2. Apply migrations:**

```bash
# from inside the app container
docker compose exec app alembic upgrade head

# or locally if running outside Docker
uv run alembic upgrade head
```

**3. Restart the app container** so the lifespan handler seeds the users from `.env`:

```bash
docker compose restart app
```

You can now sign in at `https://${APP_HOSTNAME}/auth/login`.

## Running tests

Tests run against a real Postgres database (`family_assistant_test`) so SQL, ORM mappings, and pgvector behavior are exercised honestly. Each test runs inside a transaction that rolls back when it finishes — commits inside request handlers become SAVEPOINTs.

**One-time:** create the test database (the app's Postgres user owns it).

```bash
docker compose exec postgres createdb -U family_assistant family_assistant_test
```

**Run the suite:**

```bash
uv run pytest          # all tests
uv run pytest -v       # verbose
uv run pytest tests/test_auth.py::test_login_creates_session_row   # single test
```

`DATABASE_URL` must point at the same Postgres instance (the test DB name is derived by swapping the database component). The test suite does not run any Alembic migrations — it builds the schema directly from `Base.metadata` so tests are decoupled from migration history.

## Repo layout (populated as modules land)

```
src/family_assistant/
  grocery/
  meal_plan/
  lunch_plan/
  exercise/
  memory/
  assistant/
  ai_gateway/
```

Each module owns its tables, routes, AI tool definitions, and templates (PRD Section 8 / 16.3).

## License

No license set — all rights reserved. Public for visibility, not for reuse.
