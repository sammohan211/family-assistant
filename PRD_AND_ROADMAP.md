# Product Requirements Document: Family Assistant App

**Version:** 1.0 written 2026-05-16, "ready to build"; maintained since as a living spec — shipped changes are folded into their sections in-place.
**Project type:** Personal project for one household; not shipped or sold.
**Platform:** Responsive web app (phone + laptop browsers).
**Users:** Two adult accounts (pre-seeded, simple session) + non-login family-member entries (kids) for planning.
**Deployment:** Containerized on a cloud VPS (see §17).
**Cadence:** Weekend project, no deadline.

---

## 1. Overview

A household management platform for two adults coordinating groceries, meals, kids' school lunches, chores, and personal logs — with an embedded AI assistant (LLM + structured tool execution + explicit memory) that reduces interaction friction while the backend stays the source of truth for validation and data integrity.

## 2. Why I'm Building This

One place to manage the household, extensible enough to host an AI layer over our own data — existing apps each solve one narrow piece. Equally a learning project: a real, daily-use codebase for experimenting with an embedded LLM, tool execution, memory, and retrieval. The dual goal drives most tradeoffs: features must earn their place in our house, and the AI layer should teach something while staying deterministic and safe where it matters.

## 3. Product Vision

A modular household operating system that helps the household **plan, remember, and act**: what groceries do we need, what are we eating this week, what lunches need prep, what's due today, what exercise have I logged. The MVP was intentionally narrower (§7).

## 4. Goals

1. A household workspace for the two adults; mobile-first responsive (phone + laptop).
2. Modular features — each module owns its tables, routes, AI tools, and UI. No plugin framework.
3. MVP surface: grocery, meal planning, school lunches, exercise logging, assistant, memory.
4. Kids as non-login `FamilyMember` entries.
5. An assistant that parses natural language, retrieves household context, remembers preferences, and triggers safe structured actions — with deterministic backend services as the source of truth for permissions, validation, mutation.
6. Containerized, cloud-deployable. Household data protected (see §15.2 for the LLM-provider posture).

## 5. Non-Goals

1. Multi-household / multi-tenant support.
2. Child or teen logins, or child-facing interfaces.
3. Native mobile apps.
4. Medical records, diagnosis, or clinical advice (the BP module §10.9 is personal self-tracking with descriptive labels only).
5. Automatic purchasing / commerce integration; budgeting / financial management.
6. Autonomous AI agents (chains acting without per-step confirmation).
7. Document intelligence pipeline (OCR, PDF extraction).
8. An in-app calendar surface — calendar lives outside the app.
9. Production auth ceremony (verification, reset, invitations, roles).
10. PWA install, offline support, push notifications.
11. Reminders / time-based notifications (still deferred — §21 Phase 4). A shared recurring household-tasks module *did* ship post-MVP (§10.11): due dates surface overdue items in-list, but nothing notifies.

## 6. Users

**Two adults** with identical permissions — no admin/member distinction. **Non-login FamilyMembers** (kids): name, school days, notes; facts the AI uses (preferences, allergies) live in Memory (§11.7), subject-tagged to the member. Pets etc. may come later.

## 7. MVP Scope (as shipped)

Login (two pre-seeded users) · shared grocery list · weekly meal planner · school lunch planner · personal exercise logging · assistant with LLM command parsing · memory with full CRUD UI · assistant interaction log · responsive UI · containerized deployment. Vector retrieval was specced for MVP but deferred (§11.8); object storage and a generic audit log deferred (§11.9, §12).

## 8. Product Principles

1. **Mobile-first, laptop-friendly** — quick capture on phone, planning workflows on laptop.
2. **Modular by design.**
3. **AI as an input accelerator**, not a replacement for deterministic logic.
4. **Structured data is the source of truth** — LLM output is validated into backend actions; the LLM never mutates data directly.
5. **Memory is explicit and controllable** — inspect, edit, delete anything stored.
6. **Safe failure over silent mutation** — ambiguous or invalid output asks for clarification instead of changing data.
7. **Privacy by default** — household data stays in our infrastructure; LLM calls are a deliberate, contained exception (§15.2).

## 9. Core User Stories (condensed)

- **Auth:** log in with my pre-seeded account.
- **Grocery:** add items; mark purchased (and undo); categories; recent-items re-add.
- **Meals:** plan by day; reuse previous meals.
- **Lunches:** plan per kid per school day; record per-kid preferences/allergies the AI applies.
- **Exercise:** log by picking a known exercise + the numbers for its scoring type; body/muscle-group tagging; one comparable work score per session; a weekly view with deltas; body weight on my profile; assistant logging by exercise name.
- **BP:** log readings (systolic/diastolic/HR/date/time/notes); MAP computed; category labels (descriptive only); trends; private per user.
- **Hikes:** log Bruce Trail segments (section, name, map links, distance, duration); speed computed; progress view; private per user.
- **Tasks:** shared chore board; name/details/assignee; recurrence (one-off or every N days/weeks/months); one-click Done that reschedules; overdue stands out; completion history.
- **Assistant:** natural-language commands; ask what's planned; remembers preferences; memories reviewable; confirmation before risky changes.
- **Horoscopes:** *removed 2026-06-28* (built 2026-06-12, removed at the household's request — see §10.12).

## 10. Functional Requirements

### 10.1 Authentication and Access

Login/logout for the two pre-seeded accounts; server-side sessions (HTTP-only cookie); no sign-up, verification, reset, or invitations. Credentials seeded from `.env` at deployment.

### 10.2 Household

One implicit household. No household entity, creation flow, roles, or generic mutation audit log (assistant interactions are logged separately — §11.10).

### 10.3 FamilyMember (non-login)

Name, free-text notes, school days (weekdays needing a packed lunch). Preferences/allergies/restrictions live as Memory records subject-tagged to the member — one home for facts the AI uses. FamilyMembers cannot log in.

### 10.4 Grocery Module

Add/edit/delete items; purchase + undo; categories; quantity + free-form unit; notes; who-added/who-purchased tracking; recent-items quick-add; assistant-created items. **Form-level duplicate warning:** a case-insensitive name match against *open* items warns and requires a second submit; purchased history isn't matched; the assistant path isn't gated (the LLM sees the open list in context). Scheduled/recurring items: not built. Smarter dedup (synonyms, plurals, `1 dozen eggs` ≈ `12 eggs`, a `grocery.update_item` fold-in tool) is phase 2 — it needs canonical ingredient names from the catalogs.

### 10.5 Meal Planning Module

Household meals (dinner in practice; breakfast/lunch/snack slots exist). Weekly grid; entries by date + meal type with free-text title, notes, favorite flag; reuse/duplicate; assistant-created entries.

**Recipe catalog — shipped 2026-05-31** at `/meal-plan/catalog`, deliberately leaner than the original phase-2 plan: household-shared `recipes` with name, meal type, ingredient *names only* (no amounts, no FK from plan entries — entries keep free-text titles so recipes can be edited or removed without breaking history), optional instructions/notes, and coarse nullable calories + protein as a planning aid, not a tracking ledger. The meal form offers a pick-from-catalog title fill; the assistant reads the catalog in context (suggest-from-what-we-have, missing-ingredient checks) but has no recipe write tools. Still deferred: full macro set + weekly macro view, meal-to-grocery generation, pantry inventory (§21 Phase 2).

### 10.6 School Lunch Planning Module

Per-kid, per-school-day planning; entry = item list (each item optionally annotated) + notes; weekly grid showing the kid's school days (non-school days appear only if they already have an entry); the UI auto-picks the single current kid while the data model stays multi-kid; assistant-created entries. The kid's restrictions surface via Memory. `packed_status` exists in the schema (default `planned`) but isn't surfaced — the household doesn't track packing. Templates and the LLM weekly lunch planner are phase 2.

### 10.7 Exercise Module

Two tables: a household-shared **catalog** of named exercises and per-user **logs**.

1. **Catalog:** `body_group` (upper|lower|core|cardio), `muscle_groups` (free-text tags), `scoring_type` (weighted|distance|bodyweight_fraction), `bodyweight_fraction` (default 1.0; e.g. captain's chair 0.5). Not pre-seeded.
2. **Log:** one catalog exercise + date + the inputs its scoring type needs (`weighted`: sets/reps/weight; `distance`: distance_km; `bodyweight_fraction`: sets/reps); optional duration + notes.
3. **Work score**, computed at write time and **persisted** so body-weight changes don't rewrite history: `weight×reps×sets` / `distance_km×body_weight` / `body_weight×fraction×reps×sets`.
4. **Body weight** on the User profile, editable any time; used at write time; not versioned.
5. Each adult sees their own log at `/exercise` (visible to the other; no privacy flags).
6. **Weekly view** (`/exercise/weekly`): ISO-week total, per-body-group and per-muscle-group subtotals, delta vs. prior week. Per-exercise breakdown is phase 2.
7. **Assistant logging** by exercise name (case-insensitive); unknown names are a validation error, never auto-created.

### 10.8 Dashboard

Five cards: today's meals; **due household tasks** (overdue + due-today, with one-click Done — added with §10.11); this week's school lunches per kid; open grocery (count + quick-add + first items); the current user's recent assistant activity. AI-generated weekly summary card: phase 2.

### 10.9 Blood Pressure Module

Per-user reading log (`/bp`): date, optional time, systolic/diastolic (required), optional heart rate, notes. **MAP** computed at write time and persisted (`(systolic + 2×diastolic)/3`); **category** (normal → hypertensive crisis) derived on read and shown as a badge — descriptive only, never advice (§5.4). Trends at `/bp/trends`: latest, overall averages, category distribution, per-ISO-week averages. **Private per user** — deliberately stricter than exercise. No assistant tool yet (§21). In the UI, Exercise + BP + Hikes group under a **Health** nav menu.

### 10.10 Hike Log Module

Per-user Bruce Trail log (`/hike`): date, section, segment name, optional start/end map URLs and times, distance (required), duration (required), notes. Average speed computed at write time and persisted. Progress view (`/hike/progress`): total distance/count/time, average speed, per-section breakdown. Private per user. No assistant tool yet.

### 10.11 Household Tasks Module

Household-shared chore board at `/tasks` — deliberately *not* per-user. A task: name, optional details, optional sticky assignee (nullable = anyone), frequency (`once` / every N day|week|month), `next_due_date`, `active` flag (archive without delete). To-do view ordered by due date, Overdue (red) / Due today (amber) flagged, header counts. One-click **Done** appends a completion record (who/when/which due date), then archives a one-off or rolls a recurring task forward **from the completion date** (late completion doesn't pile up). History at `/tasks/history`. Dashboard card shipped (§10.8). No assistant tool yet.

Design decisions: history kept (not reset-on-done); assignee sticky (no rotation); overdue stays visible (no escalation/notification); recurrence anchors to completion date.

### 10.12 Horoscope Module — removed

Built 2026-06-12, **removed entirely 2026-06-28** at the household's request: module, templates, `scripts/build_natal_facts.py`, Skyfield/lunardate deps, the natal-facts mount; migration `0022` drops `horoscope_readings`. Design highlights, for the record: code computed all chart facts deterministically (Skyfield + DE421; Vedic/Chinese/Western), the LLM wrote prose grounded strictly in supplied facts; birth data never left the laptop (derived facts only, in a gitignored mounted file); readings were lazily generated and cached per period window. Not planned to return; full spec in git history.

### 10.13 Lessons Module (kids' home learning)

Shipped 2026-06-29 (migration 0023) at `/lessons` — parent-curated learning for a kid, built for summer holidays; **the kid never logs in**. Household-shared (either adult edits). A **Lesson** (title, optional subject/description, status planned|in progress|done, optional date window) contains: ordered **learning objectives** (`done` + optional `scheduled_date` to spread across days), **resources** (label + link/note, attached to the lesson), and **exactly one test** (title, done, optional score/notes) — checking off the test is what completes the lesson. Decisions: always a final test; light per-objective `scheduled_date`, no calendar primitive; no FamilyMember FK (single-kid household; revisit if that changes); UI-only, assistant tools deferred. Distinct from lunch planning (food) and Projects (an adult's own initiatives).

### 10.14 Projects Module (personal tracker)

Shipped 2026-06-29 (migration 0024, PR #2) at `/projects` — per-user, private. A **Project** (name; status idea|active|on hold|done|abandoned; optional goal, target date) has a **journal** of dated entries (note + optional link — no time/effort tracking, decided out) and dated, ordered **milestones** (title, optional target date, done + done-at). Completing a milestone auto-writes a journal line. No subtasks, no recurrence (recurring things belong to Household Tasks). UI-only; assistant tooling (`project.log_progress`, milestone tools, reads) deferred. Distinct from Memory (static facts) and Tasks (shared, recurring).

## 11. Embedded AI, Memory, and Retrieval

### 11.1 AI Objective

The assistant parses commands, retrieves household context, recalls stored preferences, summarizes on request, and safely triggers structured actions — always subordinate to deterministic app logic, schema validation, and confirmation rules. The LLM never mutates data directly.

### 11.2 AI Capabilities

Natural-language parsing; intent classification; entity extraction (dates, names, items, quantities); structured JSON conforming to published schemas; clarifying questions on ambiguity; context-grounded responses (memory + recent app data pre-loaded into the prompt); on-demand summarization; safe tool execution through backend services; full interaction logging (§11.10).

### 11.3 Example Commands

"Add milk, apples, and bread to the grocery list." · "Plan pasta for dinner on Tuesday." · "Pack a turkey sandwich and apple for Leo on Wednesday." · "Log 30 minutes of cycling today." · "What can I make for dinner with what we have?" · "What is planned for tomorrow?" · "Remember that Maya does not like egg salad."

### 11.4 LLM Role

Understand language, map to intents, extract entities, produce schema-valid JSON, and generate summaries from retrieved context on request. Nothing else.

### 11.5 Tool Execution

Current tool set (expand as flows demand — §21): `grocery.add_items`, `grocery.mark_purchased`, `meal_plan.create_entry`, `lunch_plan.create_entry`, `exercise.log_activity`, `memory.create`, `memory.search`. Every call must pass: Pydantic schema validation → authentication → module business rules (e.g. lunch entries need an existing FamilyMember) → the clarification policy (§11.5a) → the confirmation policy (§11.6).

### 11.5a Clarification Policy

Honest UX: never claim to have done something the system didn't do; never pester for schema-optional fields.

1. **Optional fields missing** → don't ask; sensible silent defaults ("add milk and bread" → two name-only items).
2. **Genuinely ambiguous** → return `tool_calls: []` + a short clarifying question. Ambiguity includes: multiple matching records in context; a required-by-schema field absent; conflict with a hard-restriction memory; an exercise name not in the catalog; self-contradicting quantities.
3. **Server-side validation failure** → the gateway overwrites any optimistic reply (the LLM sometimes says "added" for a malformed call) with a clarification request, and logs `error_log`.

Phasing: **Phase 1 (shipped)** — worked prompt examples per module. **Phase 2** — one self-repair retry feeding the validation error back to the LLM. **Phase 3** — multi-turn clarification threads (`thread_id`, `pending_clarification` status). 2 and 3 are backlog (§21).

### 11.6 Confirmation Policy

- **Low — execute immediately after validation:** reads; single-entry creates; mark/unmark purchased; a single non-hard-restriction memory.
- **Medium — confirm first:** bulk (more than 3 items or more than 3 tool calls in one request); any update to an existing entry; any single delete. *(Update/delete tools don't exist yet; the bulk rules are live in `risk.py`.)*
- **High — confirm with a clear summary:** bulk delete; creating, deleting, or modifying a hard-restriction memory.

The UI presents medium/high as a confirmation card with the proposed calls and Approve / Cancel.

### 11.7 Memory

Explicit, inspectable, editable. All memory is user- or assistant-created on request; inferred memories (AI guessing from usage) are phase 2 with review.

- **Subject:** `household` | `user` | `family_member` (+ subject_id).
- **Type:** `preference` | `food_preference` | `restriction` | `routine` | `planning_constraint` | `frequently_used`.
- **Fields:** content (free text), `is_hard_restriction` (inviolable; edits/deletes follow the High tier — allergies are the canonical case), source, tags, timestamps.
- Full CRUD + keyword search + subject/type/tag filters. Archiving/expiration: phase 2.

### 11.8 Vector Retrieval — deferred

pgvector was the MVP plan (embed memory content + plan notes; background generation; synchronous retrieval). **Not built:** household memory counts are small enough that the ~50 most recent memories go straight into the prompt. The `pgvector/pgvector:pg16` image keeps the door open; embeddings become a clean additive migration when scale demands (§21 Phase 3).

### 11.9 Object Storage — deferred

No uploads, attachments, or images anywhere. S3-compatible storage arrives with phase 2/3 ingestion features.

### 11.10 AssistantInteraction Logging

Two granularities, together the primary AI debugging surface:

- **`AssistantInteraction`** — one row per call: timestamp, user, raw input, reply (possibly gateway-overwritten), proposed tool calls, confirmation status (auto | pending_confirmation | approved | cancelled), executed calls + outcomes, affected record IDs, latency, error_log.
- **`InteractionTrace`** — one row per pipeline-stage event (input, context, llm, validation, risk, decision, execution, persist, confirm, cancel): `stage`, `event`, monotonic `ts_ms`, free-form JSONB payload (adding fields needs no migration). Indexed on (interaction_id, ts_ms) — one ordered scan reconstructs a request.
- **Trace viewer** at `/assistant/interactions/{id}/trace`: vertical timeline, stage pills, expandable payloads. Owner-only; another user's id 404s (not 403) to avoid leaking existence.

## 12. Data Model

Single implicit household; no Household/HouseholdMember/AuditLog entities. Authoritative schema: `alembic/versions/` (0001–0024) and each module's `models.py`. Summary of entities and their non-obvious decisions:

- **User** ×2, seeded from `.env`; carries `body_weight` for exercise scoring.
- **FamilyMember** — name, notes, school_days. Preferences/allergies live in Memory, not columns.
- **GroceryItem** — name, category, quantity, unit, status open|purchased, notes, added_by/purchased_by.
- **Recipe** (§10.5) — name (unique), meal_type, ingredients (JSONB list of names), optional instructions/notes, coarse nullable calories/protein_g. No FK from plan entries.
- **MealPlanEntry** — date, meal_type, free-text title, notes, is_favorite, created_by.
- **LunchPlanEntry** — family_member FK, date, items (JSONB `{name, notes?}` list), notes, packed_status (unsurfaced), created_by.
- **Exercise** (catalog) + **ExerciseLog** — per §10.7; `work_score` persisted at write time so later body-weight edits don't distort history.
- **BloodPressureReading** — per §10.9; `map_value` persisted, category derived on read.
- **Hike** — per §10.10; `speed_kmh` persisted.
- **HouseholdTask** + **HouseholdTaskCompletion** — per §10.11; completion log is append-only; task denormalizes last_completed for display; assignee FKs `ON DELETE SET NULL`.
- **Lesson / LearningObjective / LessonResource / LessonTest** — per §10.13.
- **Project / ProjectMilestone / ProjectEntry** — per §10.14.
- **Memory** — per §11.7; `subject_type`/`subject_id` is polymorphic (no FK — orphan cleanup deliberately punted, see §21 notes).
- **AssistantInteraction / InteractionTrace** — per §11.10.
- ~~EmbeddingRecord~~ — never built (§11.8). ~~HoroscopeReading~~ — dropped by migration 0022 (§10.12).

## 13. Permissions Model

No roles. Both adults have identical capabilities; the only API-layer check is "authenticated user". Per-user privacy where it exists (exercise log, BP, hikes, projects, assistant history) is ownership scoping, not roles. RBAC is a phase-5 concern, deliberately not designed in.

## 14. User Experience Requirements

**Phone:** quick actions — add/purchase grocery, assistant input, today's plan, log exercise. Large touch targets, simple daily views. **Laptop:** planning workflows — weekly meal/lunch grids, list management, memory review. **Assistant UX:** typed commands; clarifying questions; confirmation cards for medium/high risk; execution feedback with links to affected records. Voice input deferred.

## 15. Non-Functional Requirements

### 15.1 Security

HTTPS-only in production; Argon2id password hashing; server-side sessions (HTTP-only, Secure, SameSite cookies); validation at every API and tool boundary; CSRF on all state-changing endpoints; parameterized queries; no third-party log shipping.

### 15.2 Privacy

Household data is private by default; memories are inspectable/editable/deletable. **LLM posture (revised 2026-06-28):** the original PRD required a self-hosted LLM with no third-party calls. The home-GPU/Ollama stack was retired and the app is now OpenRouter-only — an explicit, deliberate opt-in: prompts (including household context and memories) leave the network to the chosen provider, mitigated by picking models/providers with no-retention policies. Data export/deletion workflows remain designed-in but unbuilt.

### 15.3 Performance

Common screens fast on phone Wi-Fi (<2 s); sub-second-feeling grocery interactions; simple assistant commands target <3 s end-to-end; the app degrades gracefully when the LLM is unavailable — everything except the assistant keeps working.

### 15.4 Reliability

Automated daily DB backups with rotation and off-box copies (see `OPERATIONS.md`); forward-only migrations with a pre-migrate dump in the deploy script; structured error logging; health checks per container; core modules stay usable during AI outages.

### 15.5 Accessibility

Readable typography, sufficient contrast, keyboard navigation where practical, large tap targets, no precise-gesture-only workflows.

## 16. Technical Architecture

### 16.1 High-Level

One FastAPI app (auth, module routers, HTML rendering, in-process AI Gateway) → Postgres (+pgvector image, unused vector features) — with LLM calls going out to OpenRouter over HTTPS. See `ARCHITECTURE.md` for the code-level map. The gateway is isolated behind a module boundary so it could become a sidecar service later.

### 16.2 Frontend

Server-rendered Jinja2 + HTMX (lightly used) + Alpine.js + Tailwind via CDN. No SPA, no bundler. Mobile-first responsive.

### 16.3 Backend

FastAPI (Python 3.11+), SQLAlchemy 2.x, Alembic, Pydantic v2 (tool schemas + settings), session cookie auth. One package per feature module. Background workers: none needed yet.

### 16.4–16.6 Data stores

PostgreSQL 16 (pgvector image); a single database. Dedicated vector DB: not warranted at household scale. Object storage: deferred (would be S3-compatible — R2/S3/MinIO).

### 16.7 AI Gateway

In-process module (`ai_gateway/`): prompt building with pre-fetched context; LLM calls through the `LLMClient` Protocol — `OpenRouterClient` (OpenAI-compatible `/chat/completions`, JSON response format) or the offline `MockLLMClient` when `USE_MOCK_LLM=true`; Pydantic tool validation; dispatch into module service layers; confirmation policy (§11.6); interaction logging + per-stage tracing (§11.10). Entry point `process_command(user, input_text)` consumed by the assistant router.

### 16.8 Model Runtime

**OpenRouter** (cloud, per-token) — sole runtime since 2026-06-28; the model is `OPENROUTER_MODEL` in `.env`, chosen for JSON-output reliability and a no-retention provider policy. The original design ran Ollama in a sidecar container on a home GPU box (with a planned local embedding model); it was retired along with `compose.yml`/`compose.gpu.yml` — history in git. The offline mock (`llm_mock.py`) survives unchanged: keyword-driven scenarios plus `force_mode` failure hooks, each paired with the defense layer it exercises.

## 17. Deployment

**Live topology (since 2026-06): a single cloud VPS (Hetzner)** running `compose.cloud.yml` — app + Postgres + Caddy (Let's Encrypt against the public domain), chat via OpenRouter. Config via `.env`; healthchecks + `restart: unless-stopped`; deploy/rollback/backup scripts in `scripts/` (see `OPERATIONS.md`).

The PRD originally specced two topologies — home GPU box first (Tailscale + internal CA + local Ollama), cloud later — kept portable via env-only differences. That migration happened and the home topology was retired 2026-06-28; the portability discipline that made it a config swap (named volumes, no hardcoded hostnames, `APP_BASE_URL`, Caddy in front in all cases) still stands. §§17.1–17.9 detail from the two-topology era is in git history.

Still-relevant evolution options: managed Postgres, dedicated object storage when phases land. Kubernetes is explicitly not on this roadmap.

### 17.10 Shared edge: multi-tenant Caddy (live since 2026-07-12)

The cloud VM hosts more than this app, and the Caddy service in `compose.cloud.yml` is the shared edge for all of it. This repo owns the edge; every other site on the VM is a tenant. (The old monolithic Caddyfile was migrated on 2026-07-12; a backup sits at `/root/family-assistant/Caddyfile.bak.2026-07-12`, and the step-by-step migration record is in git history — `git log -- CADDY_ROBUSTNESS_RUNBOOK.md`.)

**Topology:**

1. **`caddy_net` is load-bearing infrastructure.** An external Docker network created once (`docker network create caddy_net`), owned by no compose project — never remove it. Containerized tenants join it and pin a container name (`<app>-app`, e.g. `options-app`); Caddy reaches them only through it.
2. **One site file per tenant.** The main Caddyfile ends with `import sites/*.caddy`; tenant site blocks live in `/root/family-assistant/sites/` on the VM. Each tenant app's own repo is the source of truth for its site block (e.g. options-helper's `caddy/options.Caddyfile`), so the `.caddy` files are deliberately not committed here — only `sites/README.md` is tracked, to keep the directory present for the compose bind mount. The main Caddyfile changes only for cross-cutting concerns.
3. **Static tenants need no containers.** `/root/static/<app>/` on the host is mounted read-only into Caddy at `/srv/static`; the site block is just `root * /srv/static/<app>` + `file_server` (+ `basic_auth` where wanted). Content updates need no reload — only site-file changes do. Live static tenants: `books.` (directory `browse`) and `notes.` (basic-auth-gated HTML built from private LyX sources; that pipeline is documented in the notes repo's own README — `/data/Notes` locally, rsynced to `/root/static/notes/`).

**Adding a tenant:** containerized — join `caddy_net` and pin the container name in the app's compose file; static — drop content under `/root/static/<app>/`. Either way, add `/root/family-assistant/sites/<app>.caddy` (domain, `tls {$CADDY_TLS}`, then proxy or file_server), then validate + reload. DuckDNS resolves any subdomain automatically, so there is no DNS step.

**Operational notes:**

- After any `sites/` change, always validate before reloading:
  ```bash
  docker exec family-assistant-caddy-1 caddy validate --config /etc/caddy/Caddyfile
  docker exec family-assistant-caddy-1 caddy reload  --config /etc/caddy/Caddyfile
  ```
- The main Caddyfile is a single-file bind mount: editors/sed that replace the file (new inode) leave the container reading the old copy. If a reload doesn't take, recreate Caddy (`docker compose -f compose.cloud.yml up -d --force-recreate caddy`). Files inside `sites/` don't have this problem — the whole directory is mounted.
- Bare `docker compose` breaks in `/root/family-assistant`: the global `COMPOSE_FILE` in `/root/.bashrc` points at the options repo. Always pass `-f compose.cloud.yml` there.
- Recreating the Caddy container is safe for all tenants — networks and mounts are declared in compose, nothing is runtime-only.
- Optional later cleanup: extract Caddy + `sites/` into a standalone `edge/` stack so family-assistant becomes an ordinary tenant. Ownership nicety only; robustness doesn't depend on it.

## 18. Success Metrics

**Lived utility (subjective):** both adults open the app weekly unprompted; the in-app grocery list is the actual shopping list; meal and lunch planning happen in-app before the week starts.

**AI quality (measurable from the interaction log):** command success rate; parse-failure rate; confirmation acceptance rate; median/p95 latency; memory CRUD counts over time.

**Operational:** LLM provider reachable; most recent successful backup, restore rehearsed at least once.

## 19. Risks and Mitigations

- **Scope creep** → §5 is binding; §21 is where extra ideas go.
- **LLM reliability** → JSON response format + Pydantic validation on every call + confirmation tiers + full logging; invalid output asks for clarification instead of guessing.
- **LLM dependency & cost** → cloud per-token pricing on a cheap model; the manual UI is fully usable without the assistant; provider/model swappable via `.env` (model snapshots get retired — a 404 means pick a listed one).
- **Privacy** → see §15.2; memories inspectable/deletable; logs stay inside the deployment.
- **Ops complexity for a solo builder** → one compose file, one database, scripted deploy/backup/rollback, no Redis/queue/object storage until a real need.
- **Mobile friction kills adoption** → mobile-first quick actions; assistant input as fast capture.
- **Weekend-only progress** → module-by-module, each shippable alone.

## 20. Open Questions — resolved

All build-time questions have answers now: model = whatever `OPENROUTER_MODEL` picks (JSON-reliable, currently-listed; originally an Ollama model bake-off); embedding model = moot (embeddings deferred); JSON enforcement = provider JSON mode + Pydantic; GPU vs CPU = moot (cloud API); provider = Hetzner; auth = hand-rolled minimal session cookies (no `fastapi-users`).

## 21. Backlog and Future Roadmap

**Near-term backlog** (unphased; when an item ships, delete it here and update its PRD section in-place):

- **Expand assistant tool coverage as needs surface** — update/delete/duplicate variants when a real flow demands them, not to complete the matrix.
- **Assistant read support for exercise history** — an `exercise.search`-style tool + prompt-builder pre-fetch, so "how much did I run this week?" works.
- **Clarification Phase 2** — one self-repair retry on validation failure (§11.5a).
- **Clarification Phase 3** — multi-turn threads (`thread_id`, `pending_clarification`).
- **Deterministic eval set** — `tests/eval/` of (input, expected_tool_calls) pairs scored 0–1; catches prompt regressions on model changes.
- **Output guardrails as a named pipeline layer** — consolidate the scattered blank-field/FK/confirm checks into one `output_guardrails(...) → ALLOW | BLOCK | ESCALATE | FALLBACK` step.
- **Assistant tools + dashboard cards for BP, hikes, tasks, lessons, projects** — these modules shipped UI-only by design; add write tools (`bp.log_reading`, `hike.log_hike`, `task.add`/`task.complete`, `project.log_progress`, ...), read support, and cards (latest BP, trail progress) when a flow demands them. (The tasks dashboard card already shipped — §10.8.)
- **`USER_NAME` cosmetic** — pending cleanup from the cloud migration.

**Deferred decisions:** pgvector image stays although unused (free phase-3 option). Memory `subject_id` orphans (polymorphic, no FK) — revisit only if orphans surface in the UI.

**Phase 1 — MVP:** ✅ shipped (see §7).

**Phase 2 — Better Planning:** the *lean* recipe catalog shipped (§10.5); still open: full macros + weekly macro view; pantry inventory / "what's in stock" hints; plannability gate (cross-check a picked meal's ingredients against open + recently-purchased at plan time, one-click add-missing); meal-to-grocery generation; LLM weekly lunch planner (restrictions + macro targets + variety → M–F proposal feeding grocery); a guided **weekly planning workflow** bundling meals + lunches + grocery with a printable one-page summary and post-shopping reconcile; LLM grocery dedup via `grocery.update_item` (needs catalog canonical names); lunch templates; AI weekly summary card; PWA; memory archiving; inferred memories with review.

**Phase 3 — AI and Retrieval Expansion:** object storage; recipe/document ingestion; semantic search (the deferred embeddings, §11.8); recommendations from history + preferences; model upgrades / hybrid routing; voice input.

**Phase 4 — Broader Household Operations:** household tasks ✅ (§10.11), projects tracker ✅ (§10.14), kids' lessons ✅ (§10.13), horoscopes ❌ built-then-removed (§10.12). Still open: reminders/time-based notifications (re-evaluate — the household has lived without them); one-way calendar export of planned meals/lunches; budget-adjacent planning; pet care; elder care.

**Phase 5 — Beyond One Household:** multi-household; teen logins; child-friendly views; guest/read-only roles.
