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
