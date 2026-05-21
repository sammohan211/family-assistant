# Bug Review

Review basis: [`PRD_AND_ROADMAP.md`](PRD_AND_ROADMAP.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the current implementation under `src/`.

## Findings

- **Assistant tool execution can still persist blank records** — The assistant tool schemas accept plain `str` fields for names/titles/content, and the downstream service layer only trims before commit instead of rejecting empty-after-trim values. An LLM-produced tool call like `{"name": "   "}` or `{"content": "   "}` can therefore create blank grocery items, meal entries, lunch items, or memories even though the HTML forms block those inputs. Affected areas include `ai_gateway/tools.py` plus service-layer creates in `grocery/services.py`, `meal_plan/services.py`, `lunch_plan/services.py`, and `memory/services.py`.
- **Several edit routes report success for missing records** — Some POST update routes call service methods that return `None` when the row no longer exists, but the routers ignore that and always redirect as if the edit succeeded. A stale tab or deleted record therefore looks like a successful save with no change applied. Affected routes include family member, grocery, meal plan, lunch plan, and memory update handlers.

## Resolved

- **Test suite errored at collection without `.env`** — `tests/conftest.py`'s session-scoped `engine` fixture previously called `get_settings().database_url`, which triggered full Pydantic validation of every required setting (`session_secret`, `app_base_url`, ...) before any test could run. Now reads `DATABASE_URL` directly from `os.environ` and `pytest.fail`s with an instructive message if it's missing — matches the lazy spirit of `db.get_engine()`.
- **Assistant history leaked across users on `/assistant` and `/dashboard`** — `ai_gateway/services.list_recent_interactions` now requires a keyword-only `user_id` and filters by it (no default, so the safety can't recur). The `/assistant` and `/dashboard` index routes inject the current user via `Depends(require_user)` and pass `user.id`. Regression test added in `tests/test_assistant.py::test_recent_interactions_are_scoped_per_user`: user A submits a known phrase, user B logs in via a fresh `TestClient`, and both pages are asserted not to contain it.
- **Invalid assistant tool output routed into the approval flow** — the gateway now routes validation-errors-only responses to `auto` with an `error_log` and a clarification reply; `confirm_pending` early-returns when there is nothing valid to execute.
- **`memory.create` from the assistant bypassed subject validation** — `memory.services` now backstop-validates the subject FK in both `create_memory` and `update_memory`; the assistant tool handler returns a `validation_error` `ToolResult` on mismatch.
- **Hard-restriction memories editable or deletable with no confirmation gate** — `update_memory`/`delete_memory` require `confirmed=True`; the UI routes hard-restriction deletes through a dedicated confirmation page and renders a required acknowledgement checkbox on the edit form.
- **Any authenticated user could approve or cancel any pending assistant interaction** — `get_interaction` now scopes by `user_id`; confirm/cancel routes pass the current user.
- **Deleting a family member with lunch-plan rows failed at commit time** — `delete_family_member` raises `FamilyMemberInUseError` with the dependent count; the router catches it and re-renders the edit form with a `409` and a friendly message.
- **Import-time settings loading broke test collection without `.env`** — `db.py` now exposes `get_engine()` and `get_sessionmaker()` (lazy, `lru_cache`'d); engine construction happens at first use, not at module import. `main.py` updated to match. `tests/test_settings_bootstrap.py` is a subprocess-level regression guard.

## Verification Notes

- Source review confirms the resolved items above are implemented in the current codebase.
- Full DB-backed runtime verification was not possible in this environment because `DATABASE_URL` was unset, so pytest integration tests that require Postgres could not run here.
