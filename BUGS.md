# Bug Review

Review basis: [`family_assistant_prd.md`](family_assistant_prd.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the current implementation under `src/`.

## Findings

### 1. Medium: Import-time settings loading makes the app and tests fail before startup when `.env` is absent

- Evidence:
  - [`src/family_assistant/db.py:15`](src/family_assistant/db.py#L15) calls `get_settings()` at import time and builds the engine immediately.
  - Running `uv run pytest` fails during import with a `Settings` validation error for `database_url`, `session_secret`, and `app_base_url`, before test collection begins.
- Impact:
  - The test suite is not runnable in a clean checkout unless a fully populated `.env` already exists.
  - This is inconsistent with the documented testing flow and makes local verification brittle because configuration errors surface during module import rather than controlled startup.

## Resolved

- **Invalid assistant tool output routed into the approval flow** — the gateway now routes validation-errors-only responses to `auto` with an `error_log` and a clarification reply; `confirm_pending` early-returns when there is nothing valid to execute.
- **`memory.create` from the assistant bypassed subject validation** — `memory.services` now backstop-validates the subject FK in both `create_memory` and `update_memory`; the assistant tool handler returns a `validation_error` `ToolResult` on mismatch.
- **Hard-restriction memories editable or deletable with no confirmation gate** — `update_memory`/`delete_memory` require `confirmed=True`; the UI routes hard-restriction deletes through a dedicated confirmation page and renders a required acknowledgement checkbox on the edit form.
- **Any authenticated user could approve or cancel any pending assistant interaction** — `get_interaction` now scopes by `user_id`; confirm/cancel routes pass the current user.
- **Deleting a family member with lunch-plan rows failed at commit time** — `delete_family_member` raises `FamilyMemberInUseError` with the dependent count; the router catches it and re-renders the edit form with a `409` and a friendly message.
