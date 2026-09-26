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
4. Medical records, diagnosis, or clinical advice (the BP module §10.9 and the Blood Sugar module §10.15 are personal self-tracking with descriptive labels only).
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
- **Blood Sugar:** log glucose readings (value/context/date/time/notes); context-aware category labels (descriptive only); trends with charting; single-user only — unlike BP/Hikes' per-user ownership scoping, this module is not reachable at all by the other adult (§10.15).
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

1. **Catalog** (re-modelled by §10.16 step 1, migration `0026`): `region` (upper|lower|core|full), `modality` (strength|cardio), `location` (gym|home|both), `primary_muscles` / `secondary_muscles` from a fixed 16-muscle vocabulary (`exercise/taxonomy.py`; at least one primary), `scoring_type` (weighted|distance|bodyweight_fraction|timed), `bodyweight_fraction` (default 1.0; e.g. captain's chair 0.5). Not pre-seeded; `scripts/seed_exercises.py` seeds the reviewed catalog on a fresh install. The catalog form uses muscle checkboxes; the list flags exercises with no muscles.
2. **Log:** one catalog exercise + date + the inputs its scoring type needs (`weighted`: sets/reps/weight; `distance`: distance_km; `bodyweight_fraction`: sets/reps; `timed`: duration, distance optional); optional duration + notes. The new-log form shows the last session's values as greyed placeholders, a "Last time … score" line, and a "Use last values" button.
3. **Work score**, computed at write time and **persisted** so body-weight changes don't rewrite history: `weight×reps×sets` / `distance_km×body_weight` / `body_weight×fraction×reps×sets` / `duration minutes`. The weight used is stored as `body_weight_used`, and editing a log re-scores with it rather than today's weight. Scores are only comparable within one exercise; the household goal is simply to meet or beat the last session's score.
4. **Body weight** on the User profile, editable any time; used at write time; not versioned.
5. Each adult sees their own log at `/exercise` (visible to the other; no privacy flags).
6. **Weekly view** (`/exercise/weekly`): built from the §10.16 weekly summaries: sets per muscle, cardio minutes, balance, days since trained, per-exercise progress, each vs the prior week. `work_score` is never summed across exercises.
7. **Assistant logging** by exercise name (case-insensitive); unknown names are a validation error, never auto-created.

**Audit 2026-09-26 — limitations found** (all fixed: tags, cardio-as-body-group, unused duration and edit re-scoring by §10.16 step 1; incomparable totals by step 2): free-text muscle tags copied from gym-machine labels merge opposing muscles (`biceps and triceps`, `chest upper and middle back`) and several are wrong or synonyms; the three scoring types produce incomparable numbers, so the weekly totals and deltas are dominated by strength work (a ~3 h hike scores under half a set of curls); `cardio` is modelled as a body group, so cardio never counts toward the legs; `duration_minutes` is unused; `update_log` re-scores an edited log with the *current* body weight, contradicting item 3.

### 10.8 Dashboard

Five cards: today's meals; **due household tasks** (overdue + due-today, with one-click Done — added with §10.11); this week's school lunches per kid; open grocery (count + quick-add + first items); the current user's recent assistant activity. AI-generated weekly summary card: phase 2. A **training priorities** card with a Refresh button (§10.16 step 3) spans the top row for users with exercise logs in the last 4 weeks.

### 10.9 Blood Pressure Module

Per-user reading log (`/bp`): date, optional time, systolic/diastolic (required), optional heart rate, notes. **MAP** computed at write time and persisted (`(systolic + 2×diastolic)/3`); **category** (normal → hypertensive crisis) derived on read and shown as a badge — descriptive only, never advice (§5.4). Trends at `/bp/trends`: latest, overall averages, category distribution, per-ISO-week averages. **Private per user** — deliberately stricter than exercise. No assistant tool yet (§21). In the UI, Exercise + BP + Hikes group under a **Health** nav menu, joined by Blood Sugar (§10.15) — though that entry is visible only to its designated owner, not to both adults.

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

### 10.15 Blood Sugar Module

Shipped 2026-09-20 (migration `0025`). Per-user glucose reading log at `/glucose`, mirroring the BP module's shape (§10.9): date, **optional time** (kept optional, matching BP — friction reduction matters more than precision, and the context tag already carries most of the "when in the day" signal), reading value in **mg/dL only** (required — no mmol/L support; US convention, matches the owner's glucometer), a reading-context tag, optional free-text notes (per-reading, same as BP — this is what the chart tooltip surfaces, e.g. what was eaten).

**Context tags — three, each with UI helper subtext so picking one is unambiguous:**
- `fasting` — "No food or drink (except water) for 8+ hours, typically first thing in the morning"
- `after_meal` — "About 2 hours after starting a meal"
- `random` — "Any other time — spot-check, bedtime, etc."

**Category label — context-aware, unlike BP's single fixed scale** (fasting and post-meal have genuinely different normal ranges, so one scale would mislead): derived on read, shown as a badge, descriptive only, never advice, same posture as BP (§5.4).
- `fasting`: normal <100, elevated 100–125, high 126+
- `after_meal` and `random`: normal <140, elevated 140–199, high 200+ (random borrows the after-meal scale — the standard ADA reference for an unqualified "random glucose" reading)

**Medication/insulin dose: explicitly out of scope** — reading + context + notes only, consistent with the medical-records non-goal (§5.4); anything ad hoc can go in the notes field.

**In-app charting at `/glucose/trends`** (Chart.js + the date-fns adapter, via CDN — the app's first charting library, fits the existing CDN-only frontend, no bundler): a scatter chart of readings over time (x = date/time, y = mg/dL), one series per context tag (fasting/after_meal/random, distinct colors), tooltip on each point showing its note text. Chosen over exporting to an external tool (Sheets/Excel) specifically because this module's privacy motivation (owner-only) would be undercut by round-tripping the data through a third-party spreadsheet. Alongside the chart: latest reading, overall average, category distribution, per-context averages, per-ISO-week averages — parallel to `/bp/trends`.

**Restricted to a single specific user — not just private-per-user like BP/Hikes, but invisible and unreachable to the other adult entirely.** This is the app's first whole-module single-user restriction, a deliberate, narrow departure from §13's "no roles, both adults identical" permissions model. **Owner is hardcoded to `settings.user1_email`** (no dedicated setting — avoids unneeded config surface for a single fixed owner). Implementation, built fresh (no prior precedent for whole-module restriction — see §13):

- `glucose/router.py::require_owner` compares the authenticated user's email against `settings.user1_email`; the non-owner gets a **404, not 403**, on every route — reusing the existence-hiding pattern already used for the assistant trace viewer (§11.10).
- The nav entry (desktop dropdown + mobile list in `base.html`) is hidden for the non-owner via a new Jinja context global, `templating.py::is_glucose_owner`, gated on `request.state.user_email` — which `auth/dependencies.py::require_csrf` (already a global per-request dependency) now stashes for every logged-in request, alongside its existing `csrf_token` stash. UX-only; the router dependency is the real gate.
- No prefill of "today" on the date field (matching BP, which has none either), so the server/household timezone mismatch flagged during design never becomes a bug in practice — if a "today" quick-fill is ever added, it must be set client-side (`new Date()` in the browser), never server-rendered.

Data model: `GlucoseReading` — per-user (`user_id` FK, `ondelete="CASCADE"`), same shape as `BloodPressureReading` (§12) plus a `context` column. No assistant tool, consistent with how BP/Hikes shipped UI-only (§21).

### 10.16 Training Guidance — designed 2026-09-26; steps 1–3 built, step 4 planned

**Goal:** passive weekly hints on what to train. At the start of a week the user presses **Refresh** on a dashboard card and gets 2–3 priorities — body area, muscles, and exercise options split by gym and home. Hints only: no workout plans, no nagging, never medical advice (§5.4). Primary user is one adult; the card is per-user, so the other adult gets their own if they log exercise.

**Principle — code decides, the LLM phrases** (same pattern as the removed horoscope, §10.12): all numbers, rankings and exercise candidates are computed deterministically; the LLM only selects among them, groups them and writes a one-line reason, and its output is validated against the catalog.

**Data decisions (from the household):**
- Units are **lb** throughout, body weight included. A dumbbell `weight` is the **total of both** dumbbells; single-arm moves (Single Arm Row, Concentration curl, Triceps kickback) log the one dumbbell.
- Training happens at the **gym and at home** (dumbbells, sit-ups, push-ups, a cardio rowing machine).
- **Only the exercise log's `Hiking` entries** are used for training analysis. The Hike module (§10.10) is a Bruce Trail credit tracker and is not read, so nothing is counted twice.

#### Step 1 — Catalog re-model and re-tag migration (no LLM) — built (migration `0026`)

As built, beyond the spec below: old `body_group`/`muscle_groups` are dropped once the defaults are derived; exercises not in the re-tag table get `region` from their old body group (`cardio` → `full`), `modality` cardio if they were cardio or distance-scored, `location` both, and no muscles (flagged in the catalog until picked). If "Row Machine" had logs it stays the gym seated row and "Rowing machine" is added alongside. The downgrade restores the old columns approximately. `tests/test_exercise_migration.py` exercises upgrade and downgrade on an old-format catalog.

**Fixed muscle vocabulary** (16), replacing the free-text tags:

| Group | Muscles |
|---|---|
| Upper push | `chest`, `front_delts`, `side_delts`, `triceps` |
| Upper pull | `upper_back`, `rear_delts`, `biceps`, `forearms` |
| Core | `abs`, `lower_back`, `hip_flexors` |
| Lower | `quads`, `hamstrings`, `glutes`, `adductors`, `calves` |

**`exercises` changes:**
- Add `primary_muscles` and `secondary_muscles` (JSONB lists, validated against the vocabulary).
- Add `region` (`upper` | `lower` | `core` | `full`), `modality` (`strength` | `cardio`) and `location` (`gym` | `home` | `both`).
- Add a `timed` scoring type: `work_score = duration_minutes`, and duration is required. All cardio exercises use it (distance stays optional input).
- Retire `body_group` and the free-text `muscle_groups`.

**`exercise_logs` changes:**
- Add `body_weight_used`, set at write time.
- Editing a log re-scores it with its own `body_weight_used`, not the user's current weight.

**Re-tag table** (applied by a hand-written data migration). Primary muscles count as 1 set each, secondary as ½. Cardio rows list the muscles whose "last trained" date they update; they don't add strength sets.

| Exercise | Region | Primary | Secondary | Where | Scoring |
|---|---|---|---|---|---|
| Chest press machine | upper | chest | triceps, front_delts | gym | weighted |
| Pec fly machine | upper | chest | front_delts | gym | weighted |
| Dumbbell bench press | upper | chest | triceps, front_delts | both | weighted |
| Flat Dumbbell Press | — | *duplicate of Dumbbell bench press; deleted (0 logs)* | | | |
| Pushups | upper | chest | triceps, front_delts, abs | home | bodyweight 0.64 |
| Dumbbell shoulder press | upper | front_delts | side_delts, triceps | both | weighted |
| Shoulder press machine | upper | front_delts | side_delts, triceps | gym | weighted |
| Front raise | upper | front_delts | — | both | weighted |
| Lateral Raise | upper | side_delts | — | both | weighted |
| Triceps pushdown | upper | triceps | — | gym | weighted |
| Triceps extension machine | upper | triceps | — | gym | weighted |
| Triceps kickback | upper | triceps | — | both | weighted |
| Overhead Dumbbell Triceps Extension | upper | triceps | — | both | weighted |
| Lat pulldown | upper | upper_back | biceps, rear_delts | gym | weighted |
| Seated Cable Row | upper | upper_back | biceps, rear_delts | gym | weighted |
| Single Arm Row | upper | upper_back | biceps, rear_delts | both | weighted |
| Rear Delt Pec Fly Machine | upper | rear_delts | upper_back | gym | weighted |
| Hammer Curl | upper | biceps | forearms | both | weighted |
| Barbell curl | upper | biceps | forearms | gym | weighted |
| Seated dumbbell curl | upper | biceps | forearms | both | weighted |
| Concentration curl | upper | biceps | — | both | weighted |
| Arm curl machine | upper | biceps | forearms | gym | weighted |
| Sit-ups | core | abs | hip_flexors | home | bodyweight 0.38 |
| Abdominal machine | core | abs | hip_flexors | gym | weighted |
| Captain's Chair Leg Raise | core *(was lower)* | abs, hip_flexors | — | gym | bodyweight 0.5 |
| Leg raise | core | abs, hip_flexors | — | gym | weighted |
| Leg Raise unweighted | core | abs, hip_flexors | — | both | bodyweight 0.4 |
| Back Extension Machine | core | lower_back | glutes, hamstrings | gym | weighted |
| Hack squat | lower | quads | glutes, adductors | gym | weighted |
| Leg press | lower | quads, glutes | hamstrings, adductors | gym | weighted |
| Leg extension | lower | quads | — | gym | weighted |
| Leg curl | lower | hamstrings | calves | gym | weighted |
| Dumbbell squat | lower | quads, glutes | adductors | both | weighted |
| Romanian Dead Lift | lower | hamstrings, glutes | lower_back, forearms | both | weighted |
| Kettle Bell Swing | lower *(was core)* | glutes, hamstrings | lower_back, abs | both | weighted |
| Hiking | full · cardio | *recency:* quads, glutes, calves | — | outdoors (`both`) | timed |
| Treadmill | lower · cardio | *recency:* calves | — | gym | timed |
| StairMaster | lower · cardio | *recency:* quads, glutes, calves | — | gym | timed |
| Row Machine → **Rowing machine** | full · cardio | *recency:* upper_back, quads | — | home | timed |

`Row Machine` was a never-logged weighted entry. It is repurposed as the home cardio rowing machine (renamed, re-typed).

**Effect on existing logs:**
- Log rows are not modified. Muscles, region, modality and location live only on the catalog and are read at query time, so past weeks are re-interpreted with the corrected tags.
- Saved `work_score` values stay as they are, except cardio logs, which are re-scored to minutes from their stored `duration_minutes`; logs without a duration score 0.
- `body_weight_used` is backfilled with the user's current weight (an approximation).
- **As deployed (2026-09-26):** 17 of 22 Hiking logs and all 3 Treadmill logs turned out to have no duration (the audit's "~195 min" average covered only the 5 that did), so they scored 0. The owner approved estimates, applied by hand after the migration to that user's 18 logs: at least 4 km at trail pace (3.2 km/h, or that day's Hike-module pace), under 4 km at 5 km/h walking pace. Each is marked `(duration est.)` in its notes. The other adult's two duration-less hikes were left at 0.
- The `exercise_logs → exercises` FK is `ON DELETE RESTRICT`, so no exercise with logs can be deleted by mistake. The two deletions above have 0 logs.
- Take a manual backup immediately before deploying.

#### Step 2 — Weekly state summary (no LLM) — built (migration `0027`, `exercise/summary.py`)

One **TrainingWeekSummary** row per (user, ISO week), holding a JSONB snapshot computed from that week's exercise logs:
- `active_days`
- `strength_sets` per muscle: primary = 1 × logged sets, secondary = ½ × logged sets
- `balance`: push vs pull sets; upper vs lower vs core sets
- `cardio_minutes`, total and per exercise
- `days_since_trained` per muscle, as of week end (strength and cardio recency both count)
- per-exercise best `work_score` and change vs the previous time, for progress only

`work_score` is never summed across exercises. It is only compared with earlier logs of the same exercise.

**Lifecycle:**
- Summaries are built **lazily** when a completed week without one is requested. No scheduler. The current week is always built live, marked partial, and measured as of today; a completed week is measured as of its Sunday.
- Creating, editing or deleting a log deletes the stored summary for that log's week **and every later week**, since later weeks' "days since trained" and "vs previous" can depend on it. Any catalog edit or delete drops all stored summaries (it re-interprets every week). They are rebuilt on next use.
- Each summary stores a `version`; a summary from an older version is rebuilt on read, so changing the shape never needs a data migration.
- Strength logs without a set count count as one set. Cardio adds minutes and recency, never sets.
- `/exercise/weekly` now shows active days, strength sets and cardio minutes (each vs the prior week), push/pull/core/lower balance, sets and days-since-trained for every muscle (never-trained or 7+ days highlighted), cardio minutes per exercise, and per-exercise progress. The summed `work_score` total is gone.

#### Step 3 — Dashboard training-priorities card (LLM)

The card is per-user and shows the stored result for the current ISO week. Before the first refresh of a week, it shows a Refresh prompt. It is hidden for users with no exercise logs in the last 4 weeks.

**Pressing Refresh:**
1. Ensure summaries exist for the **last 4 complete weeks**, plus the current week so far, marked as partial. Including the partial week means a mid-week refresh won't re-suggest something already done on Monday.
2. **Rank muscles deterministically.** Signals, in rough order:
   - days since last trained
   - sets vs the user's own 4-week average, plus a small per-muscle floor (a tunable constant, initially about 4 sets/week) so never-trained muscles still surface
   - push/pull balance and upper/lower balance
   - cardio minutes vs the 4-week average

   There are no fixed weekly quotas. For each top muscle, collect the matching catalog exercises (primary first) split by `location`.
3. **One LLM call** through the AI gateway (§16.7), JSON output validated with Pydantic (§19). The input is the summaries, the ranking and the candidate exercises. The output is 2–3 priorities, each with a body area, muscles, a one-line reason, gym options and home options. An optional "keep it up" line is allowed.
4. **Validate the answer.** Exercise names not in the catalog and muscles not in the vocabulary are dropped. If nothing valid remains, fall back to step 6.
5. Store the result in **TrainingPriorities** (user, `week_start` unique per user, content JSONB, model, generated_at, `is_fallback`). Refreshing again overwrites it, so there is at most one LLM call per press.
6. **Fallback.** If the LLM is unavailable or its output is invalid, the card shows the top of the deterministic ranking with its candidate exercises and no prose.

**As built (2026-09-26, `exercise/priorities.py`, migration `0028`):**
- **Score per muscle** = 0.5 × need + 0.5 × staleness.
  - Need is the share of this week's target not yet done; the target is the higher of the 4-week average and the floor (`SET_FLOOR` = 4 sets).
  - Staleness is days since trained, capped at 14.
  - A muscle whose target is already met scores 0.
  - The weaker side of push/pull or upper/lower gets +0.15 when below 75% of the stronger.
  - Trained today or yesterday: × 0.5. Never trained: × 0.6, so it surfaces without outranking a muscle you've let slip.
- **Areas:**
  - Areas are the four muscle groups plus Cardio. Cardio scores 0.8 × its minutes shortfall vs the 4-week average (floor 60 min).
  - An area's score is its top muscle's score. It lists up to 3 muscles within 60% of that score.
  - Areas below 0.35, or with no catalog options, are dropped; at most 3 are kept.
  - Each option is ranked by how much of the area's need it covers: the sum of its muscles' scores, primary in full and secondary at half. A row that hits the lead muscle therefore outranks a curl that only touches forearms. Options are capped at 5 per location. `both` counts for gym and home.
- **LLM call:**
  - It uses the LLM client directly (`chat_json`), like the old horoscope feature. It does not go through `process_command`, since no tools are involved.
  - The LLM only picks among the ranked areas and their candidates.
  - Validation also drops unknown areas and duplicates.
  - Every priority carries a factual code-built reason (e.g. "Chest: last trained 9 days ago; 0 of ~6 sets this week"). This is the fallback's text and fills in a missing LLM reason.
  - "Keep it up" lists exercises that met or beat their last score.
- **Card and routes:**
  - The card spans the dashboard's top row. Refresh posts to `/exercise/priorities/refresh`.
  - A week with nothing to rank shows "on track" and is not a fallback.
  - `USE_MOCK_LLM` uses a canned echo client.

**Privacy:** each user's card reads only their own logs. Blood Sugar and BP are not inputs (their privacy and advice rules would need their own decision).

#### Step 4 — later

- Mid-week progress ticks on the card, e.g. "upper back: 4 of ~6 sets" (deterministic).
- An assistant chat tool that reads the same weekly summaries. This also covers the "exercise history read" backlog item (§21).

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

Single implicit household; no Household/HouseholdMember/AuditLog entities. Authoritative schema: `alembic/versions/` (0001–0028) and each module's `models.py`. Summary of entities and their non-obvious decisions:

- **User** ×2, seeded from `.env`; carries `body_weight` for exercise scoring.
- **FamilyMember** — name, notes, school_days. Preferences/allergies live in Memory, not columns.
- **GroceryItem** — name, category, quantity, unit, status open|purchased, notes, added_by/purchased_by.
- **Recipe** (§10.5) — name (unique), meal_type, ingredients (JSONB list of names), optional instructions/notes, coarse nullable calories/protein_g. No FK from plan entries.
- **MealPlanEntry** — date, meal_type, free-text title, notes, is_favorite, created_by.
- **LunchPlanEntry** — family_member FK, date, items (JSONB `{name, notes?}` list), notes, packed_status (unsurfaced), created_by.
- **Exercise** (catalog) + **ExerciseLog** — per §10.7; `work_score` persisted at write time so later body-weight edits don't distort history. Catalog uses fixed-vocabulary primary/secondary muscles + region/modality/location; logs carry `body_weight_used` (§10.16 step 1). **TrainingWeekSummary** (§10.16 step 2): one JSONB snapshot per user per completed ISO week, unique on (user, week). **TrainingPriorities** (§10.16 step 3): one row per user per ISO week, overwritten on Refresh.
- **BloodPressureReading** — per §10.9; `map_value` persisted, category derived on read.
- **GlucoseReading** — per §10.15; per-user like BloodPressureReading, but reachable only by one designated owner (route-level check + hidden nav entry) — the app's first whole-module single-user restriction rather than ownership scoping.
- **Hike** — per §10.10; `speed_kmh` persisted.
- **HouseholdTask** + **HouseholdTaskCompletion** — per §10.11; completion log is append-only; task denormalizes last_completed for display; assignee FKs `ON DELETE SET NULL`.
- **Lesson / LearningObjective / LessonResource / LessonTest** — per §10.13.
- **Project / ProjectMilestone / ProjectEntry** — per §10.14.
- **Memory** — per §11.7; `subject_type`/`subject_id` is polymorphic (no FK — orphan cleanup deliberately punted, see §21 notes).
- **AssistantInteraction / InteractionTrace** — per §11.10.
- ~~EmbeddingRecord~~ — never built (§11.8). ~~HoroscopeReading~~ — dropped by migration 0022 (§10.12).

## 13. Permissions Model

No roles. Both adults have identical capabilities; the only API-layer check is "authenticated user". Per-user privacy where it exists (exercise log, BP, hikes, projects, assistant history) is ownership scoping, not roles — any authenticated adult can reach the routes, each just sees their own rows. RBAC is a phase-5 concern, deliberately not designed in.

**Exception: the Blood Sugar module (§10.15) is restricted to one specific named user**, not just ownership-scoped — the other adult can't reach it at all (404, not 403). This is a narrow, deliberate one-off carve-out for a personal-health module, not a reintroduction of roles/RBAC.

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
- **Training guidance (§10.16)** — designed 2026-09-26: (1) ✅ catalog re-model + re-tag migration, (2) ✅ weekly state summaries, (3) ✅ dashboard training-priorities card with LLM refresh, (4) later: mid-week progress ticks + assistant chat tool over the same summaries.
- **BP and Blood Sugar monitor/nudge cards (§10.9, §10.15)**: idea from 2026-09-26, not designed yet. The plan is dashboard cards like the training priorities card (§10.16 step 3): code computes, the LLM only phrases, with a deterministic fallback. **Prerequisite:** a few weeks of real readings; neither module is in use yet.
  - **Code decides:** it compares readings to fixed guideline ranges and to the user's own baseline or trend, and flags gaps in logging consistency. The LLM never judges whether a reading is concerning.
  - **Nudges are about habits.** Examples: "no fasting reading in 5 days", "evenings running higher than mornings", "logged BP 4 of 7 days". A high reading or rising trend says "worth raising with your doctor". There is no diagnosis or medication talk (non-goal §5.4).
  - **Open decisions:**
    - Whether readings may be sent to the LLM provider at all, or only aggregates (the §10.16 privacy note excluded them pending this).
    - Blood Sugar stays owner-only (§10.15), so its card shows only for the owner.
  - **Possible later:** correlating training weeks (§10.16 summaries) with BP/glucose trends, once months of both exist.
- **Assistant read support for exercise history** — an `exercise.search`-style tool + prompt-builder pre-fetch, so "how much did I run this week?" works. Should read the §10.16 weekly summaries rather than raw logs once they exist.
- **Clarification Phase 2** — one self-repair retry on validation failure (§11.5a).
- **Clarification Phase 3** — multi-turn threads (`thread_id`, `pending_clarification`).
- **Deterministic eval set** — `tests/eval/` of (input, expected_tool_calls) pairs scored 0–1; catches prompt regressions on model changes.
- **Output guardrails as a named pipeline layer** — consolidate the scattered blank-field/FK/confirm checks into one `output_guardrails(...) → ALLOW | BLOCK | ESCALATE | FALLBACK` step.
- **Assistant tools + dashboard cards for BP, hikes, glucose, tasks, lessons, projects** — these modules shipped UI-only by design; add write tools (`bp.log_reading`, `hike.log_hike`, `task.add`/`task.complete`, `project.log_progress`, ...), read support, and cards (latest BP, trail progress) when a flow demands them. (The tasks dashboard card already shipped — §10.8.) Blood Sugar (§10.15) is deliberately excluded from this list for now — its whole point is owner-only privacy, so an assistant tool there needs its own explicit decision, not a default "expand coverage" pass.
- **`USER_NAME` cosmetic** — pending cleanup from the cloud migration.

**Deferred decisions:** pgvector image stays although unused (free phase-3 option). Memory `subject_id` orphans (polymorphic, no FK) — revisit only if orphans surface in the UI.

**Phase 1 — MVP:** ✅ shipped (see §7).

**Phase 2 — Better Planning:** the *lean* recipe catalog shipped (§10.5); still open: full macros + weekly macro view; pantry inventory / "what's in stock" hints; plannability gate (cross-check a picked meal's ingredients against open + recently-purchased at plan time, one-click add-missing); meal-to-grocery generation; LLM weekly lunch planner (restrictions + macro targets + variety → M–F proposal feeding grocery); a guided **weekly planning workflow** bundling meals + lunches + grocery with a printable one-page summary and post-shopping reconcile; LLM grocery dedup via `grocery.update_item` (needs catalog canonical names); lunch templates; AI weekly summary card; PWA; memory archiving; inferred memories with review.

**Phase 3 — AI and Retrieval Expansion:** object storage; recipe/document ingestion; semantic search (the deferred embeddings, §11.8); recommendations from history + preferences; model upgrades / hybrid routing; voice input.

**Phase 4 — Broader Household Operations:** household tasks ✅ (§10.11), projects tracker ✅ (§10.14), kids' lessons ✅ (§10.13), horoscopes ❌ built-then-removed (§10.12). Still open: reminders/time-based notifications (re-evaluate — the household has lived without them); one-way calendar export of planned meals/lunches; budget-adjacent planning; pet care; elder care.

**Phase 5 — Beyond One Household:** multi-household; teen logins; child-friendly views; guest/read-only roles.
