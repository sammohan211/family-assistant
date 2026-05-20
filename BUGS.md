# Bug Review

Review basis: [`PRD_AND_ROADMAP.md`](PRD_AND_ROADMAP.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the current implementation under `src/`.

Verification note: the previously listed bugs appear fixed in the current codebase. I also ran `pytest -q`; the suite did not complete because of a new shared-fixture settings bug described below.

## Findings

- **Test suite still fails without env vars because `tests/conftest.py` eagerly loads settings** — the app import bug is fixed in `src/family_assistant/db.py`, but the shared `engine` fixture now calls `get_settings().database_url` at session setup, so a clean `pytest -q` still errors with missing `database_url`, `session_secret`, and `app_base_url` before most tests run. This regresses the “works without `.env` at collection/startup” goal for local testing and CI bootstrap. Repro: run `pytest -q` in a repo checkout without a populated `.env`. Relevant code: `tests/conftest.py`, `src/family_assistant/settings.py`.
- **Assistant history is leaked across users on both `/assistant` and `/dashboard`** — `get_interaction(..., user_id=...)` now protects confirm/cancel, but read paths still call `list_recent_interactions(db, limit=...)` with no user filter. That helper returns global `AssistantInteraction` rows ordered by recency, so any authenticated user can read another user’s assistant prompts/replies from the assistant page and dashboard. Relevant code: `src/family_assistant/assistant/router.py`, `src/family_assistant/dashboard/router.py`, `src/family_assistant/ai_gateway/services.py`.

## Resolved

- **Invalid assistant tool output routed into the approval flow** — the gateway now routes validation-errors-only responses to `auto` with an `error_log` and a clarification reply; `confirm_pending` early-returns when there is nothing valid to execute.
- **`memory.create` from the assistant bypassed subject validation** — `memory.services` now backstop-validates the subject FK in both `create_memory` and `update_memory`; the assistant tool handler returns a `validation_error` `ToolResult` on mismatch.
- **Hard-restriction memories editable or deletable with no confirmation gate** — `update_memory`/`delete_memory` require `confirmed=True`; the UI routes hard-restriction deletes through a dedicated confirmation page and renders a required acknowledgement checkbox on the edit form.
- **Any authenticated user could approve or cancel any pending assistant interaction** — `get_interaction` now scopes by `user_id`; confirm/cancel routes pass the current user.
- **Deleting a family member with lunch-plan rows failed at commit time** — `delete_family_member` raises `FamilyMemberInUseError` with the dependent count; the router catches it and re-renders the edit form with a `409` and a friendly message.
- **Import-time settings loading broke test collection without `.env`** — `db.py` now exposes `get_engine()` and `get_sessionmaker()` (lazy, `lru_cache`'d); engine construction happens at first use, not at module import. `main.py` updated to match. `tests/test_settings_bootstrap.py` is a subprocess-level regression guard.
