# Family Assistant

Household management web app with an embedded AI assistant. Personal project for one household.

## Stack

- FastAPI + SQLAlchemy 2.x + Pydantic v2 on PostgreSQL 16 (+ pgvector)
- Jinja2 + HTMX + Alpine.js + Tailwind — server-rendered, no separate frontend build
- Ollama sidecar for the LLM
- Docker Compose; same containers at home (GPU) and cloud (CPU)

## Docs

- [`PRD_AND_ROADMAP.md`](PRD_AND_ROADMAP.md) — what the app does, plus near-term backlog and phased roadmap (§21)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how the code fits together
- [`SETUP.md`](SETUP.md) — turn a desktop into the deployment host (Omarchy + RTX 3090)
- [`OPERATIONS.md`](OPERATIONS.md) — day-to-day ops (updates, logs, backups, model switching)
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
