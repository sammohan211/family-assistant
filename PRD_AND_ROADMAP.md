# Product Requirements Document: Family Assistant App

**Version:** 1.0 — ready to build (2026-05-16)  
**Project type:** Personal project for one household; not shipped or sold  
**Primary platform:** Responsive web app  
**Users:** Two adult accounts (pre-seeded, simple session), plus non-login entries for other family members (kids) for planning purposes  
**Deployment model:** Containerized; portable between home machine and rented cloud VM (home is the initial target). See Section 17.  
**Build cadence:** Weekend project, no hard deadline  

---

## 1. Overview

The Family Assistant App is a household management platform that helps two adults coordinate the groceries, meals, kids' school lunches, and exercise logging that run our house — with dedicated weekend planning sessions as a primary workflow.

The product is accessible from phone and laptop browsers through a responsive web interface. Two adults log in; kids and other family members are represented as non-login entries used for planning purposes (school lunches, food preferences, allergies, schedule notes).

A core element of the product is an embedded AI layer that reduces interaction friction. The AI layer includes a lightweight LLM, structured tool execution, vector retrieval, and explicit household and user memory. The assistant lets the adults interact naturally with the system, while the backend remains the source of truth for business logic, validation, and data integrity.

---

## 2. Why I'm Building This

I want a single place to manage our household — groceries, meals, kids' lunches, reminders, tasks, exercise — that fits how we actually work. Existing apps each solve one narrow piece (groceries OR recipes OR reminders) and aren't extensible enough to host an embedded AI layer over our own household data.

I'm also building this as a learning project: a real, daily-use codebase to experiment with an embedded LLM, tool execution, household memory, and vector retrieval against data I actually care about. The dual goal — real utility AND learning — drives most tradeoffs in this PRD: features should earn their place by being useful in our house, and the AI layer should be substantial enough to teach me something while staying deterministic and safe where it matters.

---

## 3. Product Vision

The Family Assistant App will become a modular, extensible household operating system for adult family members. The MVP is intentionally narrower than this vision — see Section 7 for what is in scope first.

The app should make it easy to answer and act on questions such as:

- What groceries do we need?
- What are we eating this week?
- What school lunches need to be prepared?
- What needs to be done today?
- What reminders or tasks are coming up?
- What exercise have I logged this week?

The long-term vision is to combine structured household data, AI-assisted natural language interaction, semantic retrieval, and explicit memory into a unified system that helps the household **plan, remember, and act**.

---

## 4. Goals

The product should:

1. Provide a household workspace for the two adults in the household.
2. Work well on phone and laptop browsers (mobile-first responsive). Tablet and desktop browser are not explicit MVP targets.
3. Provide modular household features that can expand over time. *Modular* here means: each feature module owns its own tables, API routes, AI tools, and UI; there is no shared plugin framework or generic module loader.
4. Support grocery tracking, meal planning, school lunch planning, exercise logging, reminders, and tasks in the MVP.
5. Represent kids as non-login family member entries for planning purposes.
6. Include an embedded AI assistant that can parse natural language, retrieve household context, remember preferences, and trigger safe structured actions.
7. Use deterministic backend services as the source of truth for permissions, validation, and data mutation.
8. Be containerized and deployable to rented cloud infrastructure.
9. Protect private household and preference data; avoid sending it to third-party LLM providers by default.

PWA installation is deferred to phase 2.

---

## 5. Non-Goals

The MVP will not attempt to provide:

1. Multi-household / multi-tenant support. The app serves one household.
2. Child or teen login accounts, or child-facing interfaces.
3. A native iOS or Android app.
4. Medical record storage, medical diagnosis, or clinical health advice.
5. Automatic grocery purchasing or any external commerce integration.
6. Budgeting or financial management.
7. Complex autonomous AI agents (chains of agents acting without per-step user confirmation).
8. A full document intelligence pipeline (OCR, structured extraction from PDFs, etc.).
9. Fully on-device LLM inference or vector storage.
10. An in-app calendar surface. Calendar lives outside the app.
11. Production auth ceremony: email verification, password reset, member invitations, role hierarchies beyond a single adult role.
12. PWA installation, offline support, or push notifications in MVP.
13. Reminders, household tasks, and time-based notifications. Section 10.8 is dropped from MVP. The shopping list, meal plan, and lunch plan each carry their own to-do semantics; a separate generic task list is not needed.

---

## 6. Users

### 6.1 The Two Adults

Both adults coordinate groceries, meal planning, kids' school lunches, and exercise logging. Both have the same permissions and capabilities in the app — there is no admin/member distinction or role hierarchy in MVP.

### 6.2 Non-Login Family Members

Kids are represented as non-login `FamilyMember` entries: name, food preferences, allergies, school days, and free-form notes. These entries exist for planning purposes (especially school lunches) and do not log in or interact with the app directly. Pets and other household members may be added in later phases (see Section 21).

---

## 7. MVP Scope

The MVP shall include the following capabilities:

1. Login with two pre-seeded user accounts (simple session).
2. Shared grocery list.
3. Weekly meal planner.
4. School lunch planner using non-login FamilyMember entries.
5. Personal exercise logging.
6. Embedded assistant input with LLM-backed natural language command parsing.
7. Household and user memory with full CRUD UI (create, view, edit, delete, search).
8. Vector-backed semantic retrieval over memories (pgvector or equivalent).
9. Assistant interaction log (every user command, parsed intent, proposed action, confirmation, execution outcome).
10. Responsive web interface optimized for phone and laptop.
11. Containerized deployment.

Object storage and a generic mutation audit log are deferred — see Sections 11.9 and 12 (the `AuditLog` entity is removed in MVP; the `AssistantInteraction` log remains).

---

## 8. Product Principles

1. **Mobile-first, laptop-friendly.** The app should work very well on phones for quick capture and daily use, while supporting richer planning workflows on laptops.
2. **Modular by design.** Each feature module owns its own tables, API routes, AI tools, and UI. There is no shared plugin framework or generic module loader.
3. **AI as an input accelerator.** The assistant reduces friction but does not replace deterministic app logic.
4. **Structured data is the source of truth.** LLM outputs are validated and converted into structured backend actions; the LLM does not mutate data directly.
5. **Memory should be explicit and controllable.** Users can inspect, edit, and delete any stored memory at any time.
6. **Safe failure over silent mutation.** Invalid or ambiguous assistant outputs ask for clarification or fail without changing data.
7. **Privacy by default.** Household data stays in the app's own infrastructure. No household data is sent to third-party LLM providers in MVP.

---

## 9. Core User Stories

### 9.1 Authentication

- As an adult user, I want to log in with my pre-seeded account so I can access the household workspace.

### 9.2 Grocery Tracking

- As an adult, I want to add grocery items so the household knows what to buy.
- As an adult, I want to mark items as purchased (and undo) so the list stays current.
- As an adult, I want items grouped by category so shopping is easier.
- As an adult, I want a "recent items" section so frequently bought things are easy to re-add.

### 9.3 Meal Planning

- As an adult, I want to plan meals by day so the household knows what is coming up.
- As an adult, I want to reuse previous meals so weekly planning is faster.

### 9.4 School Lunch Planning

- As an adult, I want to plan lunches for each kid by school day so prep is easier.
- As an adult, I want to record food preferences, allergies, and restrictions per kid so the AI can apply them when I plan or pack lunches.

### 9.5 Exercise Logging

- As an adult, I want to log workouts by picking a known exercise and entering the relevant numbers (sets/reps/weight, distance, or both), so each session captures the load that was actually trained.
- As an adult, I want each exercise tagged with a body group (upper / lower / core / cardio) and one or more muscle groups, so I can later see which areas I've been hitting.
- As an adult, I want a single comparable "work score" computed per log entry from the inputs and my current body weight, so I can try to beat last week's score next time.
- As an adult, I want a separate weekly view that totals work score by body group and by muscle group with a delta vs. the previous week, so I can spot under-trained areas without doing the math myself.
- As an adult, I want my body weight stored on my profile and editable any time, so distance- and bodyweight-based scores stay accurate.
- As an adult, I want to view my own exercise history; both adults can see each other's history (no privacy controls in MVP).
- As an adult, I want the assistant to log a workout by referencing an exercise by name.

### 9.6 Embedded Assistant

- As an adult, I want to type natural-language commands so I can update the app without navigating multiple screens.
- As an adult, I want to ask what is planned today (meals, lunches) so I can quickly orient myself.
- As an adult, I want the assistant to remember household preferences so future interactions are more relevant.
- As an adult, I want to review, edit, and delete stored memories so I remain in control of what the system remembers.
- As an adult, I want the assistant to ask for confirmation before making medium- or high-risk changes so accidental commands don't disrupt plans.

---

## 10. Functional Requirements

### 10.1 Authentication and Access

The application shall support:

1. Login and logout for the two pre-seeded adult user accounts.
2. Server-side session management (HTTP-only cookie).
3. Access from phone and laptop browsers.

There is no public sign-up, email verification, password reset flow, or invitation flow in MVP. Account credentials are seeded during deployment.

### 10.2 Household

There is a single household, created at deployment time. Both pre-seeded adults belong to it. There is no household creation flow, no invitation flow, no member removal flow, no role assignment, and no admin/member distinction in MVP.

The application does not maintain a generic mutation audit log in MVP. Assistant interactions are logged separately — see Section 11.10.

### 10.3 FamilyMember (non-login)

The application shall support non-login `FamilyMember` entries used for planning purposes. A FamilyMember represents a kid in the household.

FamilyMember columns:

1. Name.
2. Notes (free text).
3. School days (which weekdays they need a packed lunch).

Facts about a FamilyMember used by the AI for planning — food preferences, allergies, dietary restrictions, dislikes — are stored as `Memory` records subject-tagged to the FamilyMember (see Section 11.7). This keeps "facts the AI uses for context" in a single home.

FamilyMember entries cannot log in. Future phases may add other non-login entities (pets, etc.) — see Section 21.

### 10.4 Grocery Module

The application shall support:

1. Add, edit, and delete grocery items.
2. Mark an item as purchased; undo (restore to unpurchased).
3. Categorize items (e.g. produce, dairy, pantry, household).
4. Quantity and unit per item.
5. Free-text notes per item.
6. Track who added and who purchased each item.
7. "Recent items" quick-add UX surfacing frequently bought items.
8. Assistant-created grocery items via the AI layer.
9. **Form-level duplicate warning on add.** A case-insensitive name match against currently open items shows a warning ("Already on the open list: X") and requires a second submit to add anyway. Purchased history is not matched. The LLM-assistant path is not gated by this — the LLM already sees the open list in its prompt context and is responsible for its own decision.

Scheduled / recurring grocery items (e.g., "milk every Tuesday") are not in MVP.

Smarter dedup — LLM-assisted matching against canonical names and units (synonyms, plurals, "1 dozen eggs" ≈ "12 eggs"), with an `grocery.update_item` tool that folds a request into an existing open item where appropriate — is deferred to phase 2. It becomes natural once the meal/lunch catalogs (§10.5, §10.6) supply canonical ingredient names; until then, structured dedup has nothing to match against.

### 10.5 Meal Planning Module

The Meal Planning Module covers household meals — breakfast, lunch (at home), dinner, snacks. Kids' packed school lunches are handled separately in Section 10.6.

The application shall support:

1. Weekly meal planning view.
2. Meal entries by date and meal type (breakfast, lunch, dinner, snack).
3. Free-text title and notes per meal.
4. Reuse / duplicate previous meals.
5. Mark a meal as a favorite (`is_favorite` flag) to filter the meal-reuse picker.
6. Assistant-created meal plan entries.

Recipe links and meal-to-grocery generation are deferred to phase 2. Also deferred: promoting meal entries from freeform titles to a household-shared **meal catalog** (mirroring the exercise catalog) with ingredients and **per-meal macronutrient values** (protein, fat, carbs, fibre). The catalog enables a weekly macro view for balancing macros across the week while planning. Macros are stored per prepared meal (one entry's worth), not per serving — there is no per-person consumption tracking; aggregation stays at the household level.

### 10.6 School Lunch Planning Module

The application shall support:

1. Lunch planning per FamilyMember (kid) by school day. Current household has one kid; the UI auto-picks the single FamilyMember (hides the selector) but the data model, assistant tool, and weekly grid stay multi-kid-capable.
2. Each lunch entry is a list of items plus free-text notes.
3. The lunch planning UI surfaces the kid's food preferences, allergies, and restrictions for reference.
4. Assistant-created lunch entries.
5. Weekly lunch overview across all kids.

Packed / not-packed status is captured in the schema (defaults to `planned`) but is not surfaced in the MVP UI — the household does not track packing. The column and the `POST /{entry_id}/status` route stay in place for forward compatibility.

Lunch templates and an LLM-assisted weekly lunch planner are deferred to phase 2. The planner — given the kid's hard restrictions (e.g., school no-nut rule + allergies from Memory), macro targets, and recent variety — proposes the coming week's five weekday lunches with grocery-feeding ingredients. Shares the macro framework with the phase-2 meal catalog (§10.5).

### 10.7 Exercise Module

The exercise module is structured as two tables: a household-wide **exercise catalog** of named, classified exercises, and per-user **exercise logs** that reference an exercise plus the numbers from one session. Each log carries a computed `work_score` so sessions are directly comparable week over week.

The application shall support:

1. **Exercise catalog (household-shared).** A named exercise has:
   - `body_group` — one of `upper | lower | core | cardio`.
   - `muscle_groups` — array of tags (e.g. `chest`, `triceps`, `quads`). Free-text in MVP; a fixed vocabulary may be introduced later. The user will populate this from an existing reference list outside the app.
   - `scoring_type` — one of `weighted | distance | bodyweight_fraction`.
   - `bodyweight_fraction` — decimal used only when `scoring_type = bodyweight_fraction` (default `1.0`; e.g. captain's chair = `0.5`).

   The catalog is **not pre-seeded** in MVP; the user adds exercises as needed.

2. **Exercise log (per user).** A log entry references one catalog exercise + a date + numeric inputs appropriate to the exercise's scoring type:
   - `weighted` → `sets`, `reps`, `weight`.
   - `distance` → `distance_km` (covers walking, hiking, running, rowing-machine distance).
   - `bodyweight_fraction` → `sets`, `reps`.

   `duration_minutes` and `notes` are optional on any entry.

3. **Work score formulas** (computed at write time and persisted on the log row, so historical scores don't drift if body weight is later updated):
   - `weighted`: `weight × reps × sets`
   - `distance`: `distance_km × body_weight`
   - `bodyweight_fraction`: `body_weight × bodyweight_fraction × reps × sets`

4. **User body weight.** Stored on the User profile, editable at any time. Used by the `distance` and `bodyweight_fraction` formulas at the moment of write. Not versioned per log.

5. **Per-user log views.** Each adult sees their own log on `/exercise`. Both adults can view each other's logs; per-entry visibility flags are out of scope.

6. **Weekly aggregation view** at a separate path (e.g. `/exercise/weekly`) showing, for the current ISO week:
   - Total work score for the week.
   - Subtotal per `body_group`.
   - Subtotal per `muscle_group`.
   - Delta vs. the previous week (absolute and %).

   A per-exercise breakdown within each body group / muscle group is deferred to phase 2.

7. **Assistant-created log entries.** The assistant can create one log entry per call by referencing an exercise by name (case-insensitive). Unknown names return a validation error rather than auto-creating a catalog entry.

### 10.8 Dashboard

The application shall provide a household dashboard showing:

1. Today's meals (from the meal planner).
2. This week's school lunches per kid, with packed status.
3. Outstanding grocery items (count + quick-add).
4. Recent assistant activity (last few interactions, links to affected records).

An AI-generated weekly summary card is deferred to phase 2.

---

## 11. Embedded AI, Memory, and Retrieval Requirements

### 11.1 AI Objective

The AI layer reduces friction by letting the adults interact with the app through natural language. The assistant parses commands, retrieves relevant household context, recalls explicitly stored preferences, summarizes plans on request, and safely triggers structured backend actions.

The AI layer is subordinate to deterministic application logic, schema validation, and user confirmation rules. The LLM never mutates application data directly.

### 11.2 AI Capabilities

The AI layer shall support:

1. Natural language command parsing.
2. Intent classification.
3. Entity extraction (dates, names, items, quantities, durations, kids).
4. Structured JSON action generation that conforms to a published schema.
5. Clarifying questions when input is ambiguous.
6. Retrieval-augmented responses backed by memory + recent app data.
7. Household and user memory retrieval (semantic + keyword).
8. On-demand summarization (e.g., "what's planned this week?").
9. Safe tool execution through backend APIs.
10. AssistantInteraction logging (see Section 11.10).

### 11.3 Example Supported Commands

Starter set; expand during implementation as more intents prove useful:

- Add milk, apples, and bread to the grocery list.
- Plan pasta for dinner on Tuesday.
- Pack a turkey sandwich and apple for Leo on Wednesday.
- Log 30 minutes of cycling today.
- What do we need to prep tonight?
- What is planned for tomorrow?
- Remember that Maya does not like egg salad.

### 11.4 LLM Role

The lightweight LLM is used for:

1. Understanding natural language.
2. Mapping requests to supported app intents.
3. Extracting entities such as dates, names, items, quantities, and durations.
4. Producing structured JSON outputs that pass schema validation.
5. Generating summaries and suggestions using retrieved context, only when explicitly requested by the user.

The LLM shall not directly mutate application data. All mutations go through validated backend services.

### 11.5 Tool Execution

The AI layer includes a tool registry that maps validated assistant outputs to backend actions. Each tool is a typed contract: parameters, JSON schema, and the backend handler it invokes.

Starter tool set (expand as needed):

1. `grocery.add_item` / `grocery.add_items`
2. `grocery.mark_purchased`
3. `meal_plan.create_entry`
4. `lunch_plan.create_entry`
5. `exercise.log_activity`
6. `memory.create`
7. `memory.search`

Every tool call must pass:

1. JSON schema validation against the published tool schema.
2. Authentication check (the call is from one of the two logged-in adults).
3. Module-specific business rules (e.g., a `lunch_plan.create_entry` call must reference an existing FamilyMember).
4. The clarification policy in Section 11.5a.
5. The confirmation policy in Section 11.6.

### 11.5a Clarification Policy

Before any tool is called, the assistant must decide whether the user's request is actionable, ambiguous, or invalid. This policy governs that decision and applies to every tool — `grocery.*`, `meal_plan.*`, `lunch_plan.*`, `exercise.*`, `memory.*` — not just grocery. The goal is honest UX: never claim to have done something the system did not actually do, and never interrupt the user for information the schema does not require.

Three cases:

1. **Schema-optional fields are missing.** The assistant must NOT ask for information that is optional in the tool's args schema. If the user says "add milk and bread," the assistant calls `grocery.add_items` with `[{name: "milk"}, {name: "bread"}]` and does not pester for quantity, unit, or category. Sensible silent defaults beat naggy prompts.

2. **The user's request is genuinely ambiguous.** When the assistant cannot resolve the request without making an arbitrary choice, it must return `tool_calls: []` and a short clarifying question in `reply`. Ambiguity includes:
   - Multiple matching records in CONTEXT (e.g., "remove the milk" when two milks are open).
   - A required-by-schema field absent from the input (e.g., "schedule dinner Saturday" with no title).
   - A request that would conflict with a hard restriction in memory (e.g., packing peanuts for a child whose memory shows a peanut restriction).
   - An exercise activity name that does not match any catalog entry case-insensitively.
   - A unit/quantity that contradicts itself or context (e.g., "log a 0-minute run").

3. **A tool call fails server-side validation.** When Pydantic rejects the assistant's proposed call, the gateway MUST overwrite any optimistic reply text (the LLM will sometimes produce "items added" even when its call was malformed) and surface a clarification request instead of letting a false-success message reach the user. The interaction must be logged with `error_log` so the failure is auditable.

**Phasing.** The clarification policy ships in three tiers; later tiers strengthen the earlier ones without breaking them:

- **Phase 1 — Prompt-time examples.** The system prompt carries worked examples of correct and ambiguous inputs for every module (one per module minimum), so the small LLM has concrete patterns to imitate. Highest leverage, cheapest change.
- **Phase 2 — Single self-repair retry on validation failure.** When validation fails, the gateway feeds the error back to the LLM once ("Your previous call failed validation: <error>. Either correct it or ask the user for clarification.") and accepts the second response. Capped at one retry to bound latency and cost.
- **Phase 3 — Multi-turn clarification threads.** `AssistantInteraction` gains a `thread_id`; a new `confirmation_status = "pending_clarification"` lets the user's next message resume the same context. Enables true conversational follow-up ("which milk?" → "the 2%" → tool call fires).

Phases 2 and 3 are explicitly out of MVP scope; Phase 1 is required for MVP behavior to feel honest.

### 11.6 Confirmation Policy

Assistant-triggered actions are classified by risk. Risk tier determines whether the user must explicitly confirm before the backend mutates data.

#### Low-Risk — execute immediately after validation

- Read queries ("What's planned today?", "What does Maya not like?").
- Single-entry creates (one grocery item, one meal, one lunch, one exercise log).
- Mark / unmark purchased on a grocery item.
- Create a single memory.

#### Medium-Risk — require confirmation before execution

- Bulk creates (more than 3 items in one call, or full-week plan generation).
- Any update to an existing entry (edit a meal, edit a lunch, edit a memory).
- Any single-entry delete.

#### High-Risk — require explicit confirmation with a clear summary of what will change

- Bulk delete (more than one entry in one call).
- Deletion or modification of a memory tagged as a hard restriction or allergy.

The assistant UI presents Medium- and High-Risk actions as a confirmation card showing the parsed intent and exact records that will be affected, with an Approve / Edit / Cancel choice.

### 11.7 Memory Requirements

The system supports explicit, inspectable, and editable memory. All memory in MVP is explicit — created by a user directly or by the assistant on the user's request. Inferred memories (the AI guessing preferences from usage patterns) are deferred to phase 2 with a review workflow.

Memory subject (who the memory is about):

1. `household` — applies to the household as a whole.
2. `user` — applies to one of the two adults.
3. `family_member` — applies to one kid.

Memory type taxonomy (starter set; expand as needed):

1. `preference` — soft preference (e.g., "we like one-pot meals on weekdays").
2. `food_preference` — likes / dislikes (e.g., "Maya does not like egg salad").
3. `restriction` — hard rule (allergies, dietary, religious). See `is_hard_restriction` below.
4. `routine` — recurring household pattern (e.g., "we usually shop Sunday morning").
5. `planning_constraint` — rule the AI must apply when planning (e.g., "no eggs on weekdays").
6. `frequently_used` — items / meals / activities that recur often.

Each memory record carries:

- Subject (subject_type + subject_id).
- Type (from the taxonomy above).
- Content (free text — the actual memory).
- `is_hard_restriction` (boolean) — when true, the memory must be treated as inviolable and any edit or deletion follows the High-Risk confirmation tier (Section 11.6). Allergies are the canonical case.
- Source (who or what created it; e.g., user, assistant, deployment seed).
- Tags (free-form labels for module association, search, etc.).
- Timestamps.

The system shall support:

1. Create, view, edit, delete a memory.
2. Search memories (keyword + semantic).
3. Tag memories by module.
4. Associate memories with subjects (household / user / family_member).
5. Store the source of every memory.

Archiving / expiration of outdated memories is deferred to phase 2.

### 11.8 Vector Retrieval Requirements

The app supports vector-based semantic retrieval for AI-assisted features. PostgreSQL with the `pgvector` extension is the MVP choice — a dedicated vector database is not used in MVP (see Section 16.5).

MVP embedding surface:

1. Memory records (content field).
2. Free-text `notes` fields on meal plan and lunch plan entries.

Other embedding surfaces (recipes, lunch templates, uploaded document chunks, past plan summaries) are introduced in later phases as the features that produce that content arrive.

Embedding generation runs in a background worker; retrieval is synchronous on the read path.

### 11.9 Object Storage

Object storage is deferred from MVP. No file uploads, attachments, or images are accepted by any MVP module. When phase 2 / 3 introduces recipes and document ingestion, S3-compatible storage will be added. The MVP architecture does not preclude this — see Section 16.6.

### 11.10 AssistantInteraction Logging

Every assistant interaction is logged at two granularities:

**Per-request (`AssistantInteraction`).** One row per assistant call, capturing the end-to-end outcome:

1. Timestamp and the user who issued the command.
2. Raw user input.
3. Parsed intent and extracted entities.
4. Proposed tool calls (JSON).
5. Confirmation status (auto / pending_confirmation / approved / cancelled).
6. Executed tool calls and their outcomes (success / validation failure / runtime error).
7. Resulting record IDs created or modified.
8. End-to-end latency.

**Per-stage (`InteractionTrace`).** Many rows per interaction, one per pipeline stage event (input, context, llm, validation, risk, decision, execution, persist, confirm, cancel). Each row stores `stage`, `event`, a monotonic offset `ts_ms`, and a free-form JSONB payload. The (stage, event) pair names *which layer* made *which* decision — so a misbehaving assistant call can be reconstructed with one query keyed on `interaction_id`, instead of re-running with print statements.

Together, these are the primary debugging surface for the AI layer — for understanding parse failures, tracing how user commands translate to database mutations, and iterating on prompts. Sensitive content (e.g., memory content quoted in inputs) should be reviewed before any future log export.

---

## 12. Data Model Draft

### 12.1 Core Entities

The data model assumes a single implicit household. There is no `Household` or `HouseholdMember` entity in MVP. If multi-household support is ever needed it is a future migration (see Section 21).

`Task`, `Reminder`, and `AuditLog` from earlier drafts are removed in MVP (reminders/tasks dropped; the AssistantInteraction log covers the AI-debugging need).

#### User

- id
- name
- email
- password_hash
- body_weight (nullable decimal; used by exercise scoring — see §10.7)
- created_at
- updated_at

Two rows, seeded at deployment.

#### FamilyMember

- id
- name
- notes (text, free-form)
- school_days (jsonb — array of weekday names)
- created_at
- updated_at

Food preferences, allergies, restrictions, and dislikes for a FamilyMember are stored as `Memory` records subject-tagged to the member — not as columns on this table.

#### GroceryItem

- id
- name
- category (e.g., produce, dairy, pantry, household)
- quantity
- unit
- status (open | purchased)
- notes
- added_by_user_id
- purchased_by_user_id (nullable)
- created_at
- updated_at

#### MealPlanEntry

- id
- date
- meal_type (breakfast | lunch | dinner | snack)
- title
- notes
- is_favorite (boolean)
- created_by_user_id
- created_at
- updated_at

#### LunchPlanEntry

- id
- family_member_id (FK → FamilyMember)
- date
- items (jsonb — array of `{name, notes?}` objects)
- notes (lunch-level notes)
- packed_status (planned | packed)
- created_by_user_id
- created_at
- updated_at

#### Exercise (catalog)

- id
- name (unique per household)
- body_group (upper | lower | core | cardio)
- muscle_groups (jsonb — array of strings; freeform tags in MVP)
- scoring_type (weighted | distance | bodyweight_fraction)
- bodyweight_fraction (decimal; only meaningful when scoring_type = bodyweight_fraction; default 1.0)
- created_at
- updated_at

Catalog is shared across both adults. Not pre-seeded; user populates as needed.

#### ExerciseLog (per-session)

- id
- user_id (FK → User)
- exercise_id (FK → Exercise)
- date
- sets (nullable int)
- reps (nullable int)
- weight (nullable decimal — for `weighted` scoring)
- distance_km (nullable decimal — for `distance` scoring)
- duration_minutes (nullable int — optional on any log)
- work_score (decimal; computed and persisted at write time using the formulas in §10.7)
- notes
- created_at
- updated_at

Persisting `work_score` is deliberate: if a user later updates their body weight, the historical score on prior log rows stays stable so week-over-week comparisons aren't retroactively distorted.

#### Memory

- id
- subject_type (household | user | family_member)
- subject_id (nullable when subject_type = household)
- memory_type (preference | food_preference | restriction | routine | planning_constraint | frequently_used)
- content (text)
- is_hard_restriction (boolean)
- source (e.g., user | assistant | deployment_seed)
- tags (jsonb — array of strings)
- created_by_user_id (nullable; null when seeded)
- created_at
- updated_at

Memories with `is_hard_restriction = true` follow the High-Risk confirmation tier for any edit or delete (Section 11.6).

#### EmbeddingRecord

- id
- source_type (memory | meal_plan_note | lunch_plan_note)
- source_id
- embedding (pgvector `vector` type)
- metadata (jsonb)
- created_at
- updated_at

Embeddings are generated in a background worker after the source record is written or updated. The retrieval path reads from this table.

#### AssistantInteraction

- id
- user_id
- created_at
- input_text
- reply (text — user-facing reply, possibly overwritten by gateway on validation failure)
- parsed_intent (jsonb)
- parsed_entities (jsonb)
- proposed_tool_calls (jsonb)
- confirmation_status (auto | pending_confirmation | approved | cancelled)
- executed_tool_calls (jsonb — array with per-call outcomes)
- affected_record_ids (jsonb)
- latency_ms (integer)
- error_log (text, nullable)

#### InteractionTrace

Per-stage observability for one `AssistantInteraction`. One row per stage event inside `process_command` / `confirm_pending` / `cancel_pending`.

- id
- interaction_id (FK → assistant_interactions.id, ON DELETE CASCADE)
- created_at
- ts_ms (integer — monotonic offset in milliseconds from request start)
- stage (string — input | context | llm | validation | risk | decision | execution | persist | confirm | cancel)
- event (string — e.g., received, built, call_started, call_succeeded, call_failed, completed, classified, auto, validation_error, pending_confirmation, interaction_saved, approved, cancelled)
- payload (jsonb — free-form per-event detail; adding fields does not require a migration)

Indexed on (interaction_id, ts_ms) so reconstructing a single request's lifecycle is one ordered scan.

---

## 13. Permissions Model

There are no roles in MVP. Both pre-seeded adult users have identical capabilities across all modules (groceries, meal plan, lunch plan, exercise log, memory, and assistant). The only access check at the API layer is "is the request from an authenticated user."

Role-based access control is a future-phase concern (see Section 21) and is intentionally not designed-in for MVP.

---

## 14. User Experience Requirements

### 14.1 Phone Experience

The phone interface supports quick actions:

1. Add grocery item.
2. Mark grocery item purchased.
3. Use assistant command input.
4. View today's plan (meals + this week's lunches).
5. Log exercise.
6. Check / mark a school lunch as packed.

Design pattern:

1. Bottom navigation.
2. Large touch targets.
3. Simple daily view.
4. Persistent or easily accessible assistant input.

### 14.2 Laptop Experience

The laptop interface supports planning workflows:

1. Weekly meal planning grid.
2. Grocery list management with category filtering.
3. Lunch planning by FamilyMember across a week.
4. Dashboard overview.
5. Bulk editing.
6. Memory review and management (list, search, edit, delete).

Design pattern:

1. Sidebar navigation.
2. Multi-column layouts.
3. Calendar-style planning views for meals and lunches (visual grid; not a calendar module).
4. Tables and filters where useful.

### 14.3 Assistant Interaction UX

The assistant is accessible through a universal input area, visible on both phone and laptop layouts.

The assistant UI shall support:

1. Typed commands.
2. Suggested actions (when the parsed intent has alternatives).
3. Clarifying questions (when input is ambiguous).
4. Confirmation cards for Medium- and High-Risk actions (Section 11.6) — showing parsed intent + records that will be affected + Approve / Edit / Cancel.
5. Execution feedback (success, validation error, runtime error).
6. Links to affected app records after execution.

Voice input is deferred to a later phase.

---

## 15. Non-Functional Requirements

### 15.1 Security

The system shall provide:

1. HTTPS-only access in production.
2. Secure password hashing (Argon2id or bcrypt with sensible parameters).
3. Secure session management (HTTP-only, Secure, SameSite cookies; server-side session store).
4. Input validation on every API and tool boundary.
5. Protection against common web vulnerabilities (CSRF on state-changing endpoints, output encoding, parameterized queries).
6. Secure handling of assistant interaction logs and memory data (no third-party log shipping in MVP).

### 15.2 Privacy

The system shall:

1. Treat household data as private by default. Public exposure is not a goal.
2. Let the adults inspect, edit, and delete any stored AI memory.
3. Never send household data to third-party LLM providers by default. The MVP uses a self-hosted LLM (Section 16.8). If a third-party LLM is ever used, it is an explicit opt-in.
4. Support future data export and deletion workflows (designed-in but not built in MVP).

### 15.3 Performance

The system should:

1. Load common phone screens quickly (target: under 2s on a typical home Wi-Fi).
2. Support fast grocery list interactions (perceived sub-second add/check-off).
3. Return common assistant command responses with low latency (target: under 3s end-to-end for a simple add/log command).
4. Use background processing for embedding generation and indexing.
5. Degrade gracefully when the AI service is unavailable — the rest of the app stays usable.

### 15.4 Reliability

The system should:

1. Run automated database backups on a schedule appropriate to the deployment (at least daily for MVP).
2. Avoid data loss during deployments (migrations run forward-compatible; downtime is acceptable for MVP).
3. Log application errors with enough context to debug.
4. Monitor service health (the LLM runtime, the app, the database).
5. Keep core app functions (grocery list, meal plan, lunch plan, exercise log) usable even if the AI service is temporarily unavailable.

### 15.5 Accessibility

The system should:

1. Use readable typography.
2. Provide sufficient contrast.
3. Support keyboard navigation where practical.
4. Use large mobile tap targets.
5. Avoid workflows that require precise gestures only.

---

## 16. Technical Architecture

### 16.1 High-Level Architecture

```text
Browser (phone + laptop)
        |
        v
+---------------------------------+
| FastAPI app                     |
|   - Auth + session              |
|   - Module routers              |
|     (grocery, meal_plan,        |
|      lunch_plan, exercise,      |
|      memory, assistant)         |
|   - HTML rendering              |
|     (Jinja2 + HTMX)             |
|   - AI Gateway (in-process)     |
+--------+----------+-------------+
         |          |
         v          v
   Postgres     Ollama (sidecar
   + pgvector   container)
                  |
                  v
              served models
              (instruct + embedding)

   ^
   |
Background worker (embedding generation)
```

The AI Gateway is in-process within the FastAPI app in MVP. Its responsibilities are isolated behind a clean Python module boundary (`ai_gateway/`) so it can be split into a sidecar service later if needed.

This logical architecture is deployment-agnostic. The same Docker Compose stack runs on either a home machine or a rented cloud VM (see Section 17). Deployment topology is selected at deploy time via env vars and compose overrides; application code is identical between targets.

### 16.2 Frontend

The frontend is server-rendered HTML with progressive interactivity. No SPA, no JS bundler complexity beyond what Tailwind requires.

Stack:

1. **Jinja2** templates for HTML rendering.
2. **HTMX** for partial-update interactions (replace fragments without full page reloads).
3. **Alpine.js** for small bits of local UI state (dropdowns, modal toggles).
4. **Tailwind CSS** for styling.
5. Mobile-first responsive layout. Phone layout uses bottom navigation; laptop layout uses sidebar navigation.

### 16.3 Backend

Stack:

1. **FastAPI** (Python 3.11+).
2. **SQLAlchemy 2.x** (or SQLModel) for ORM.
3. **Alembic** for database migrations.
4. **Pydantic v2** for request validation and AI tool schemas (shared models).
5. Session-based auth via secure HTTP-only cookies; sessions stored server-side (database or Redis).
6. Background tasks via FastAPI `BackgroundTasks` for simple cases; an ARQ or RQ worker if a real queue is needed (e.g., for embedding generation).

Project structure: each feature module is a Python package (`grocery/`, `meal_plan/`, `lunch_plan/`, `exercise/`, `memory/`, `assistant/`, `ai_gateway/`) with its own router, models, services, and (where applicable) AI tool definitions.

### 16.4 Database

- **PostgreSQL 16+**.
- **pgvector** extension for embedding storage and similarity search.
- A single database holds app data and embeddings.

### 16.5 Vector Database

pgvector inside the primary Postgres database for MVP. A dedicated vector database is not used in MVP. It would only become worthwhile if retrieval scale or performance ever required it — unlikely at single-household scale.

### 16.6 Object Storage

Object storage is deferred. When phase 2 or 3 introduces it (recipes, document ingestion, attachments), the implementation will be S3-compatible — concretely either:

1. Cloudflare R2 (cheap, no egress fees).
2. AWS S3.
3. Self-hosted MinIO if running fully on rented metal.

### 16.7 AI Gateway

The AI Gateway is a Python module (`ai_gateway/`) inside the FastAPI app. Its responsibilities:

1. Prompt template loading and rendering.
2. LLM calls via Ollama's OpenAI-compatible API (or the offline mock in `llm_mock.py` when `USE_MOCK_LLM=true`).
3. Embedding generation via Ollama's embedding endpoint (e.g., `nomic-embed-text`).
4. Retrieval orchestration over Memory + meal/lunch notes (pgvector similarity + optional keyword fallback).
5. Tool schema validation (Pydantic).
6. Tool execution dispatch into the relevant module's service layer.
7. Confirmation policy enforcement (Section 11.6).
8. AssistantInteraction logging (Section 11.10).
9. Per-stage tracing (`tracing.py`): every pipeline stage (input, context, llm, validation, risk, decision, execution, persist, confirm, cancel) emits one or more rows into `interaction_traces` keyed on the parent interaction id. See Section 11.10.

The Gateway exposes a single internal entry point (`ai_gateway.process_command(user, input_text) → AssistantInteraction`) consumed by the assistant router.

### 16.8 Model Runtime

**Ollama** running in its own container alongside the FastAPI app. Communication over Ollama's HTTP API (OpenAI-compatible).

For MVP, two models are served:

1. An **instruct model** for command parsing and summarization. Evaluation candidates: Llama 3.2 3B Instruct, Phi-3.5 mini (3.8B), Qwen 2.5 3B Instruct. Choose during build based on JSON-output reliability against the actual tool schemas. Quantized (Q4_K_M is a sensible default).
2. An **embedding model** for memory + notes embeddings. Candidates: `nomic-embed-text`, `mxbai-embed-large`.

Larger models, hybrid local/cloud routing, or task-specific model fine-tuning are deferred to later phases. Structured JSON output is enforced via either Ollama's JSON mode or a library-side constrained-decoding pass (Instructor/Outlines) — to be decided during build.

**Offline mock.** For UI development on no-GPU machines and for end-to-end tests that exercise specific failure paths without Ollama running, the same `LLMClient` Protocol is implemented by `ai_gateway/llm_mock.py`. Setting `USE_MOCK_LLM=true` in `.env` swaps in `MockLLMClient`, which routes input by keyword to canned responses and supports a `force_mode` hook (`blank_name`, `unknown_tool`, `bad_args_shape`, `hallucinated_fk`, `hard_restriction`, `bulk_grocery`, `crash`, `prompt_injection_echo`). Each failure mode is paired with the defense layer it's meant to exercise.

---

## 17. Deployment Requirements

The application is designed to run on **either a home machine or a rented cloud VM**, using the same Docker Compose stack. The intended path is to start at home (Topology B) and optionally move to cloud (Topology A) once the app is stable and daily-use reliability matters more than iteration speed. Both topologies must be reachable from the codebase with only env-var and compose-override changes — no application code differences.

### 17.1 Container Stack (identical in both topologies)

1. **FastAPI app** container — auth, modules, AI Gateway, HTML rendering.
2. **Ollama** container — serves the instruct model + embedding model.
3. **PostgreSQL 16** container with the `pgvector` extension enabled. (Cloud alternative: managed Postgres if the provider offers it with pgvector support.)
4. **Caddy** reverse proxy — provides HTTPS in both topologies (`tls internal` at home, Let's Encrypt in cloud).

Configuration is via `.env` files; secrets are passed as environment variables (no committed secrets). Each container has a health check; Compose restarts on failure. Container stdout is collected by the Docker logging driver; application errors are emitted as structured JSON.

### 17.2 Topology B: Home (initial target)

- Dedicated home box with a GPU. Not the user's daily-driver laptop. Always-on.
- UPS for graceful shutdowns through power blips.
- Remote access via **Tailscale** so the app is reachable from phones outside the home network without port-forwarding or DDNS. Works through CGNAT.
- Caddy issues internal-CA certs for HTTPS on the Tailscale hostname.
- Larger instruct model feasible (7–8B class), driven by env var. Better JSON tool-calling reliability than the 3B-class fallback.
- Backups: `pg_dump` to an off-machine destination — external drive, NAS, or a cheap cloud bucket. Daily minimum.
- Acceptable downtime: brief, occasional. The app is allowed to be down for OS updates, reboots, or hardware maintenance. The AI Gateway treats LLM unreachability as a normal error (Section 15.4).

### 17.3 Topology A: Cloud (future migration target)

- Single rented cloud VM (CPU or GPU depending on budget at time of migration).
- Caddy issues real Let's Encrypt certs against a real domain.
- Smaller instruct model if CPU-only (3B class with aggressive quantization), or the same 7–8B model if a GPU VM is rented.
- Backups: `pg_dump` to off-VM storage (S3-compatible bucket).
- Alternative: managed Postgres with pgvector support if the provider offers it — operationally simpler.

### 17.4 What Differs Between Topologies

Everything that differs between home and cloud is captured in env vars or compose overrides. Application code is identical.

| Concern | Home | Cloud | Mechanism |
|---|---|---|---|
| GPU device | Reserved | Maybe | Compose override (`compose.gpu.yml` / `compose.cpu.yml`) |
| Instruct model | 7–8B class | 3B class (CPU) or 7–8B (GPU) | `OLLAMA_MODEL` env var |
| Hostname | Tailscale name | Real domain | `APP_HOSTNAME` env var, used by Caddy |
| TLS issuer | Caddy internal CA | Let's Encrypt | Same Caddyfile, env-driven |
| Backup destination | External drive / NAS | S3-compatible bucket | `BACKUP_DEST` env var |
| Remote access | Tailscale | Public internet | Operational, no code |

### 17.5 Portability Discipline

To keep both topologies reachable as a config swap:

1. All persistence uses **named Docker volumes**; no host-path bind mounts.
2. Internal service URLs use Docker network names (e.g., `http://ollama:11434`), not `localhost`.
3. No hostnames or absolute URLs hardcoded in application code or templates; relative URLs throughout. Where an absolute URL is required, it is read from `APP_BASE_URL`.
4. Caddy fronts the app in both topologies so cookie `Secure` flag behavior is identical.
5. The AI Gateway is tested against the smallest model it might ever run, to surface JSON-reliability regressions before they hit a CPU-only cloud deployment.

### 17.6 Migration Runbook (Home → Cloud)

When the user chooses to move from Topology B to Topology A:

1. Provision the cloud VM and install Docker.
2. `pg_dump` from the home database; copy to the cloud VM; restore into the cloud Postgres volume.
3. Build or pull the application image on the cloud VM.
4. `docker compose up` with the cloud env file.
5. Point DNS at the cloud VM's IP and wait for Caddy to acquire a Let's Encrypt cert.
6. Smoke-test each module and one end-to-end assistant command.
7. Keep the home stack stopped but intact for ~one week as a rollback path.

### 17.7 Optional Additions (only if needed)

- **Redis** container for session store and/or queue work — only if `BackgroundTasks` becomes inadequate for embedding generation.

### 17.8 Operational Ergonomics

The stack has a handful of sharp edges that surface during everyday operation:

- The `COMPOSE_FILE` / GPU-overlay trap — running `docker compose up -d --build` without `compose.gpu.yml` merged silently drops GPU passthrough, sending an 8B model onto CPU and turning every assistant response into a 30–70 second wait.
- The cold-start warm-up dance — the first request after a rebuild always pays a 20–40 s model-load cost.
- Diagnostic command sprawl — `docker compose ps`, `ollama ps`, `ollama list`, `nvidia-smi`, `docker compose logs --tail=N <service>` all answer different "is it healthy?" questions, and remembering which one to reach for first is operational friction.

These are documented in `OPERATIONS.md`, but the cognitive load of remembering the right command at the right moment is real and has already caused incidents.

The project ships a single shell helper sourced from `~/.bashrc` on the desktop, providing:

1. `export COMPOSE_FILE=compose.yml:compose.gpu.yml` so plain `docker compose up -d --build` always includes the GPU overlay.
2. Short aliases for the highest-frequency operations: status check, log tails, model status, model warm-up, restart, full rebuild.
3. A single `family doctor` (or equivalent) command that runs the diagnostic chain — `docker compose ps` + `ollama ps` + `nvidia-smi` memory summary + last N app log lines — so "is it healthy?" is one keystroke.

The helper is a convenience layer; `OPERATIONS.md` remains the source of truth for what each underlying command does.

### 17.9 Future Deployment Evolutions

1. Managed container service (Fly.io, Hetzner with managed Postgres) in place of a self-managed VM.
2. Managed Postgres with managed pgvector.
3. Dedicated vector database — only if retrieval scale requires it.
4. Dedicated object storage when phase 2 / 3 lands.
5. Horizontal scaling — out of scope for personal use.

Kubernetes is explicitly not on this roadmap.

---

## 18. Success Metrics

This is a personal project, so "success" is mostly about lived experience and AI-layer quality, not product analytics.

### Lived utility (subjective)

1. Both adults open the app a few times a week without prompting.
2. The grocery list in the app is the actual list we shop from, not a fallback to notes / texts / paper.
3. Weekly meal planning happens in the app, not on paper.
4. Kids' school lunches get planned in the app before the school week starts.

### AI layer quality (measurable from the AssistantInteraction log)

1. Command success rate — share of inputs that parse to a valid tool call and execute without validation error.
2. Command parse-failure rate — share for which the LLM cannot produce valid structured output.
3. Confirmation acceptance rate — share of Medium/High-Risk proposals approved without edits.
4. Median and p95 end-to-end command latency.
5. Memory creation, edit, and delete counts over time (does memory grow and stay useful, or stagnate?).

### Operational

1. AI service uptime (Ollama up, model loaded, responding).
2. Database backup verification (most recent successful backup, restore tested at least once).

---

## 19. Risks and Mitigations

### Risk: Scope Creep

The MVP could grow too broad and stall.

Mitigation:

- Keep MVP focused on groceries, meals, kids' lunches, exercise, memory, and the assistant.
- Defer recipes, document ingestion, meal-to-grocery generation, lunch templates, and PWA to phase 2+.
- Section 5 (Non-Goals) is binding.

### Risk: LLM Reliability

The local LLM may parse commands incorrectly or produce invalid JSON.

Mitigation:

- Require structured JSON output via JSON mode or constrained decoding (Instructor / Outlines).
- Validate every tool call against its Pydantic schema before execution.
- Require confirmation for Medium/High-Risk actions.
- Log every interaction (raw input, parsed intent, executed call, outcome) to the AssistantInteraction log.
- Hard-fail gracefully — invalid output asks for clarification instead of guessing.

### Risk: LLM Latency

A small self-hosted instruct model may be slow enough to feel sluggish, especially without a GPU.

Mitigation:

- Choose models that produce JSON cleanly (Qwen 2.5, Phi 3.5, Llama 3.2 — evaluate during build).
- Use aggressive quantization (Q4_K_M or similar).
- Run on a GPU-equipped VM if budget allows; otherwise accept higher latency and use light models.
- Keep the manual UI fast — the app must be fully usable without the assistant.

### Risk: Privacy

Household data, kids' food restrictions, and assistant logs are sensitive.

Mitigation:

- All inference happens on self-hosted infrastructure. No third-party LLM calls by default.
- Memory is inspectable, editable, and deletable from the UI.
- HTTPS-only in production; secrets out of the repo.
- The AssistantInteraction log stays inside the deployment (no external log shipping in MVP).

### Risk: Infrastructure Complexity

Running a web app + Postgres + an LLM runtime + a reverse proxy on one VM is real ops work for a solo builder.

Mitigation:

- Use Docker Compose; one `docker-compose.yml` describes the whole world.
- Postgres + pgvector (no separate vector DB).
- Ollama as the LLM runtime (low operator burden).
- Defer object storage and Redis until a real need exists.
- AI Gateway in-process (one app), with a clean module boundary so it can be extracted later.

### Risk: Poor Mobile Experience

A server-rendered HTMX app on phones can feel less smooth than a React-y SPA. Daily-use friction kills personal-project adoption.

Mitigation:

- Design mobile-first quick actions (add grocery, mark purchased, log exercise, assistant input).
- Use HTMX `hx-boost` and partial swaps to avoid full-page reloads on common actions.
- Reserve laptop layouts for bulk planning workflows.
- Keep the assistant input persistent on phone — fast capture is the killer feature.

### Risk: Weekend-only progress

Personal projects with no deadline are easy to abandon mid-build.

Mitigation:

- Build module-by-module, each shippable on its own (auth → grocery → meal plan → ... → assistant).
- Don't build the AI layer until at least 2 deterministic modules are working — gives the assistant something useful to talk to.
- The MVP scope (Section 7) is the boundary. Anything beyond goes into the roadmap, not the build.

---

## 20. Open Questions

Most architectural and scope questions are resolved earlier in this PRD. What remains is build-time:

1. **Specific instruct model.** Llama 3.2 3B vs Phi-3.5 mini vs Qwen 2.5 3B Instruct — evaluate during build for JSON-output reliability against the actual tool schemas. Quantization (Q4_K_M as a starting default).
2. **Specific embedding model.** `nomic-embed-text` vs `mxbai-embed-large` — evaluate retrieval quality on actual memory content.
3. **JSON output enforcement.** Ollama's native JSON mode vs a library-side approach (Instructor, Outlines) — start with the simpler path and tighten if the LLM drifts off-schema.
4. **GPU vs CPU VM.** Profile latency for the chosen instruct model on CPU before committing to a GPU instance. Decide based on actual command latency vs cost.
5. **Cloud provider.** Pick at deployment time — Hetzner, Fly.io, Linode, others. The Docker Compose deployment is provider-agnostic.
6. **Auth library.** Roll a minimal session-cookie auth, or adopt `fastapi-users` — decide based on how much auth surface grows during build (probably minimal).

---

## 21. Backlog and Future Roadmap

Two tiers. **Near-term backlog** is the unphased queue — work picked up as needs surface, not slotted into a phase yet. **Future roadmap phases** are the strategic, multi-phase plan. When a backlog item ships, delete its bullet here and update the relevant PRD section in-place so the spec describes shipped reality.

### Near-term backlog

- **Expand assistant tool coverage as needs surface.** Starter tools cover the common write paths (grocery add / mark purchased, meal/lunch/exercise create, memory create/search). Add update/delete/duplicate variants when an actual user flow demands them, not as a "complete the matrix" exercise — §11.5 explicitly frames the starter set as something to expand during build.
- **Add assistant read support for exercise history.** Today the assistant can write exercise entries but can't answer "how much did I run this week?". This is a real gap if you want conversational reads on exercise. Needs an `exercise.search`-style tool plus extending the command-aware prompt builder to pre-fetch exercise data for exercise-flavored commands.
- **Clarification Policy Phase 2 — self-repair retry on validation failure.** Per §11.5a. When Pydantic rejects a tool call, feed the validation error back to the LLM once ("Your previous call failed validation: <error>. Either correct it or ask the user.") and accept the second response. Capped at one retry to bound latency and cost. Today the gateway is one-shot — invalid calls bounce with a generic "I couldn't act on that" reply, which wastes the LLM's ability to recover from its own shape errors.
- **Clarification Policy Phase 3 — multi-turn clarification threads.** Per §11.5a. `assistant_interactions` gains `thread_id`; a new `confirmation_status = "pending_clarification"` lets the user's next message resume the same context ("which milk?" → "the 2%" → tool fires). Needs a migration and a small router change to thread messages through `process_command`. Real conversational follow-up — today every input is independent.
- **Trace viewer admin page.** Per §17.8 and §11.10. `interaction_traces` already records per-stage events for every assistant call. Surfaces today only via direct SQL. Add a tiny admin-only HTML view at `/assistant/interactions/{id}/trace` that renders the stage sequence + payloads + latencies — turns the "why did the assistant do that?" question from a psql query into a click. Read-only, owner-only.
- **Deterministic eval set for the assistant.** A `tests/eval/` folder of `(input, expected_tool_calls)` pairs run through `MockLLMClient(force_mode=...)` or against the real LLM, with a 0–1 score. Catches prompt regressions on model upgrades. Building block already in place: `MockLLMClient` and the per-stage trace surface make pipeline-level assertions cheap.
- **Output guardrails as a named pipeline layer.** Today blank-field, FK, and confirm checks are scattered across `tools.py`, `services.py`, and `gateway.py`. Pulling them into one `output_guardrails(...) → ALLOW | BLOCK | ESCALATE | FALLBACK` step would mostly be reorganization — but it sets up a clean home for future cross-tool semantic checks (e.g., "no tool_call references a family_member_id outside the household").

### Deferred decisions / notes

- **`pgvector` image vs. plain Postgres.** Compose uses `pgvector/pgvector:pg16` but nothing in code touches vector columns or functions (embeddings deferred per scope §11.8). Leaving the image as-is costs nothing and keeps phase-2 embeddings a clean additive migration. No action unless you want to slim the image.
- **`subject_id` orphan cleanup for memories.** `Memory.subject_type` / `subject_id` is a polymorphic reference (no FK), so memories can be orphaned if a user or family member is deleted. Low real-world impact in a two-adult + few-kids household. Revisit only if orphans actually show up in the UI.

### Phase 1: MVP

1. Login for two pre-seeded adult accounts; simple server-side session.
2. Shared grocery list with categories and recent-items quick-add.
3. Weekly meal planner with favorites and meal reuse.
4. School lunch planner using FamilyMember entries.
5. Personal exercise logging.
6. Embedded assistant with LLM-backed natural-language command parsing (Ollama + small instruct model).
7. Household / user / FamilyMember memory with full CRUD UI.
8. Vector retrieval via pgvector over memory + meal/lunch notes.
9. AssistantInteraction log.
10. Dockerized deployment on a single rented cloud VM.

### Phase 2: Better Planning

1. Meal catalog (mirroring the exercise catalog): household-shared, named meals with ingredients and per-meal macronutrient values (protein, fat, carbs, fibre). Meal plan entries reference catalog meals by name. Existing freeform titles either stay as-is or are promoted into the catalog on demand.
2. Weekly macro view (`/meal-plan/weekly`) — total macros for the week plus a delta vs the prior week, used during planning. Household-level only; no per-person consumption tracking.
3. Pantry inventory and a "what's in stock" hint surfaced on the meal-plan page during planning.
4. Meal-to-grocery generation from planned meals (becomes feasible once catalog meals carry ingredients).
5. LLM-assisted weekly lunch planner: given the kid's hard restrictions (school no-nut rule, allergies from Memory), macro targets, and recent variety, proposes M–F lunches with grocery-feeding ingredients. Shares the macro framework with item 1.
6. LLM-assisted grocery dedup: a `grocery.update_item` tool plus a prompt rule that matches user requests against canonical ingredient names from the catalogs and folds same-thing-different-wording adds into the existing open row (synonyms, plurals, `1 dozen eggs` ≈ `12 eggs`). Naturally feasible once items 1 + 5 land — canonical names are the prerequisite.
7. Lunch templates.
8. AI-generated weekly summary card on the dashboard.
9. PWA installation and offline-friendly grocery list.
10. Memory archiving / expiration workflows.
11. Inferred memories with user review (the AI proposes, the user approves).

### Phase 3: AI and Retrieval Expansion

1. Object storage (S3-compatible) — Cloudflare R2 or AWS S3.
2. Uploaded recipe and document ingestion (OCR / structured extraction).
3. Semantic search over household notes and uploaded documents.
4. Stronger recommendation system (meals, lunches based on history + preferences).
5. Hybrid local/cloud LLM routing or model upgrades for harder tasks.
6. Optional voice input.

### Phase 4: Broader Household Operations

1. Chores tracking.
2. Reminders and time-based notifications (re-evaluate now that the household has lived without them).
3. Calendar integration (one-way export of planned meals/lunches to an external calendar).
4. Budget-adjacent household planning.
5. Pet care tracking.
6. Elder care routines.

### Phase 5: Beyond One Household / Beyond Adult Users

1. Multi-household support (e.g., grandparents' household, requires the migration described in Section 12).
2. Teen login accounts.
3. Child-friendly views.
4. Read-only / guest roles.
5. Age-appropriate permissions.

---

## 22. Appendix: Example Assistant Flow

### Example 1: Grocery Command (Low-Risk)

User input:

```text
Add bananas, yogurt, and oat milk to the grocery list.
```

Assistant parsed output:

```json
{
  "intent": "grocery.add_items",
  "items": [
    {"name": "bananas"},
    {"name": "yogurt"},
    {"name": "oat milk"}
  ],
  "needs_confirmation": false
}
```

Backend behavior:

1. Validate the user is authenticated.
2. Validate the payload against the `grocery.add_items` Pydantic schema.
3. Create the grocery items (3 items, under the Medium-Risk bulk threshold).
4. Write an AssistantInteraction record (input, intent, executed calls, affected IDs, latency).
5. Return success feedback with links to the new items.

### Example 2: Memory Command (Low-Risk)

User input:

```text
Remember that Maya does not like egg salad in lunches.
```

Assistant parsed output:

```json
{
  "intent": "memory.create",
  "subject_type": "family_member",
  "subject_name": "Maya",
  "memory_type": "food_preference",
  "content": "Maya does not like egg salad in lunches.",
  "is_hard_restriction": false,
  "tags": ["school_lunch"],
  "needs_confirmation": false
}
```

Backend behavior:

1. Resolve "Maya" to a `FamilyMember` row (lookup by name).
2. Validate the payload against the `memory.create` schema.
3. Insert the Memory record with `subject_type = family_member`, `subject_id = Maya.id`, `is_hard_restriction = false`.
4. Enqueue background embedding generation for the new memory.
5. Write an AssistantInteraction record.
6. Return confirmation feedback.

### Example 3: Multi-Step Planning Command (Medium-Risk)

User input:

```text
Plan lunches for Maya next week using sandwiches and fruit.
```

Assistant behavior:

1. Retrieves Maya's food preferences, allergies, and restrictions from Memory (semantic + subject filter).
2. Asks a clarifying question if needed — e.g., *"Maya doesn't like egg salad. What kinds of sandwiches should I plan — turkey, cheese, peanut butter?"*
3. After the user answers, generates a proposed plan: 5 `LunchPlanEntry` rows for Monday–Friday, each with a sandwich item and a fruit item, varying within the user's stated options.
4. Presents the plan as a confirmation card (Medium-Risk per Section 11.6: bulk create + full-week plan generation). The card shows each day, items, and notes, with Approve / Edit / Cancel.
5. On Approve, creates the 5 entries via `lunch_plan.create_entry` calls. On Edit, the user can adjust individual entries before approving. On Cancel, no records are created.
6. Every step — proposed plan, clarifying turns, final approval, executed calls — is captured in the AssistantInteraction record.
