# Bug Review

Review basis: [`family_assistant_prd.md`](family_assistant_prd.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the current implementation under `src/`.

## Findings

No outstanding findings.

## Resolved

- **Invalid assistant tool output routed into the approval flow** — the gateway now routes validation-errors-only responses to `auto` with an `error_log` and a clarification reply; `confirm_pending` early-returns when there is nothing valid to execute.
- **`memory.create` from the assistant bypassed subject validation** — `memory.services` now backstop-validates the subject FK in both `create_memory` and `update_memory`; the assistant tool handler returns a `validation_error` `ToolResult` on mismatch.
- **Hard-restriction memories editable or deletable with no confirmation gate** — `update_memory`/`delete_memory` require `confirmed=True`; the UI routes hard-restriction deletes through a dedicated confirmation page and renders a required acknowledgement checkbox on the edit form.
- **Any authenticated user could approve or cancel any pending assistant interaction** — `get_interaction` now scopes by `user_id`; confirm/cancel routes pass the current user.
- **Deleting a family member with lunch-plan rows failed at commit time** — `delete_family_member` raises `FamilyMemberInUseError` with the dependent count; the router catches it and re-renders the edit form with a `409` and a friendly message.
- **Import-time settings loading broke test collection without `.env`** — `db.py` now exposes `get_engine()` and `get_sessionmaker()` (lazy, `lru_cache`'d); engine construction happens at first use, not at module import. `main.py` updated to match. `tests/test_settings_bootstrap.py` is a subprocess-level regression guard.
