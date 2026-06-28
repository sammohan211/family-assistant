# Family Assistant

Household management web app with an embedded AI assistant. Personal project for one household.

## Stack

- FastAPI + SQLAlchemy 2.x + Pydantic v2 on PostgreSQL 16 (+ pgvector)
- Jinja2 + HTMX + Alpine.js + Tailwind — server-rendered, no separate frontend build
- LLM via OpenRouter (cloud, OpenAI-compatible API)
- Docker Compose on a cloud VPS (`compose.cloud.yml`: app + postgres + caddy)

## Docs

- [`PRD_AND_ROADMAP.md`](PRD_AND_ROADMAP.md) — what the app does, plus near-term backlog and phased roadmap (§21)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the code fits together
- [`SETUP.md`](SETUP.md) — deployment setup (§13 = current cloud/OpenRouter path; earlier sections describe the retired home-GPU box)
- [`OPERATIONS.md`](OPERATIONS.md) — day-to-day ops (updates, logs, backups)
- [`USER_GUIDE.md`](USER_GUIDE.md) — using the app
- [`BUGS.md`](BUGS.md) — bug review

## Dev setup (laptop)

```bash
uv sync --extra dev
uv run pre-commit install
cp .env.example .env
uv run pytest
```

## License

No license set — all rights reserved. Public for visibility, not for reuse.
