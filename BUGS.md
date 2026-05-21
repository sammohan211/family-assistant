# Bug Review

Review basis: [`PRD_AND_ROADMAP.md`](PRD_AND_ROADMAP.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), and the current implementation under `src/`.

## Findings

No outstanding findings.

## Resolved

- **Edit routes reported success for missing records** — `POST /grocery/{id}`, `POST /family/{id}`, `POST /meal-plan/{id}`, `POST /lunch-plan/{id}`, and `POST /memory/{id}` previously fetched the row, ignored a `None` result, called `update_*` (which silently returns `None` when the row is gone), and redirected as if the save succeeded. Each handler now early-returns a 303 to the list page when the row is missing, mirroring the GET edit_form behavior already in place. Regression tests added: one per route in `tests/test_grocery.py`, `tests/test_family_member.py`, `tests/test_meal_plan.py`, `tests/test_lunch_plan.py`, `tests/test_memory.py` — each POSTs to a non-existent ID and asserts the 303 lands on the list URL with no row created.
- **Assistant tool calls could persist blank records** — `ai_gateway/tools.py` now defines `NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` and applies it to every required identifier field (`GroceryItemArgs.name`, `MealPlanCreateEntryArgs.title`, `LunchItemArgs.name`, `ExerciseLogActivityArgs.exercise_name`, `MemoryCreateArgs.content`). Whitespace-only LLM output now fails Pydantic validation up front and flows through the existing validation-errors-only path (recorded as `auto` with `error_log`, no row created, clarification reply surfaced). Regression tests: five unit tests in `tests/test_ai_gateway.py` (one per affected field) plus an end-to-end `test_process_command_blank_required_string_does_not_stage` that asserts the gateway routing and that no `GroceryItem` is created.
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
