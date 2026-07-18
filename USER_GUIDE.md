# User Guide

Using the app once it's running (install: `SETUP.md`; ops: `OPERATIONS.md`).

Top nav: **Dashboard, Assistant, Grocery, Meal plan, Lunch plan, Tasks, Lessons, Projects, Health** (Exercise / Hikes / BP), **Family, Memory**.

## Logging in

Exactly two login users, both set via `USER1_*` / `USER2_*` in `.env`. Email + password; sessions last 30 days; **Log out** is in the nav. A forgotten password isn't recoverable — generate a new hash (`OPERATIONS.md` → Users) and `docker compose up -d app`.

## Dashboard

`/dashboard` — the landing page after login. Five cards: **today's meals**, **tasks due** (overdue and due-today household tasks, with a one-click Done), **school lunches this week** per kid, **grocery** (quick-add + first 5 open items), and **your recent assistant activity** (last 5 prompts, per user).

The grocery quick-add creates an open item with just a name; if the name already matches an open item (case-insensitive) it silently does nothing — use the full grocery page to override or set extra fields.

## Assistant

`/assistant` — type a request in plain English. The LLM picks one of three paths: answer from context (read-only questions — the prompt pre-loads relevant data, including the grocery list, this week's plans, and the recipe catalog), act immediately (low-risk), or propose actions for your approval (medium/high risk).

**The seven tools:** `grocery.add_items`, `grocery.mark_purchased`, `meal_plan.create_entry`, `lunch_plan.create_entry`, `exercise.log_activity`, `memory.create`, `memory.search`. No update/delete/rename — use the module pages for that.

**Confirmation is required for:** more than 3 tool calls in one request; more than 3 grocery items added or marked purchased in one call; creating a hard-restriction memory (allergies). Everything else runs immediately.

After a request you see the reply, a **Did:** list of executed tools with affected record IDs (`⚠` marks a per-tool failure), and a status badge (`auto` / `pending confirmation` / `approved` / `cancelled`). Confirmation-required requests show the proposed calls with **Approve / Cancel**. Each history row links to a per-stage **trace** page — the debugging view of exactly what the pipeline did.

Examples that work well:

```
Add milk, bread, and eggs to the grocery list.        → runs immediately
What can I make for dinner with what we have?         → answers from the recipe catalog + open list
Pack a sandwich and an apple for Maya's lunch Monday. → one lunch entry
Remember Alex is allergic to peanuts.                 → asks to confirm (hard restriction)
I ran 5k this morning.                                → one exercise log
```

**Dates:** prefer absolute `YYYY-MM-DD` over "this Friday" when the date matters — weekday resolution depends on the model and can land on the wrong day; the action runs, just on the wrong date.

**If something goes wrong:** "couldn't reach the assistant" → OpenRouter problem (`OPERATIONS.md` → LLM); "produced an invalid action, please rephrase" → the LLM's JSON failed validation, a rewording usually fixes it; `⚠` on one tool → that tool failed (e.g. unknown exercise name) and the inline error says why.

## Grocery

`/grocery` — the shared shopping list. Items have a name plus optional quantity (decimals fine), free-form unit, category, and notes. Per-item actions: **Purchase / Restore / Clone / Edit / Delete**. A **Recent items** section offers quick re-add of things you've bought before.

**Duplicate warning:** adding a name that case-insensitively matches an *open* item shows a warning and requires a second submit. Only exact-after-lowercasing matches count (`egg` ≠ `eggs`), purchased history isn't checked, and the assistant path isn't gated (the LLM sees the open list and makes its own call). The list is a scratchpad, not stock tracking — smarter dedup is phase 2.

## Meal plan

`/meal-plan` — household dinners on a 7-day grid (breakfast/lunch/snack slots exist but go unused here), walked with Previous/Next week. Entries have a free-text title, date, meal type, optional notes, and a favorite flag. Actions: **Edit** (Delete at the bottom of the edit page), **Reuse** (duplicate to the same day, or to a picked date from the favorites list). Below the grid: **Favorite meals** and **Recent meals** panels for fast reuse.

**Catalog** (`/meal-plan/catalog`, second tab): a household-shared recipe list — name, meal type, ingredient *names* (no amounts), optional instructions/notes, and rough calories + protein as a planning aid. The meal form's "Pick from catalog" fills the title, and the assistant uses the catalog to answer "what can I make?" and "is the grocery list enough for next week?".

Planning a meal does **not** add its ingredients to the grocery list — ask the assistant to check what's missing, or reconcile by hand.

## Lunch plan

`/lunch-plan` — packed school lunches, one week at a time, on the kid's school days (set on the Family page). Days outside `school_days` are hidden unless they already have an entry (field-trip day). An entry is a date plus items (one per line; `name: note` adds an inline note) and optional notes. With one kid, the member field auto-picks. The assistant can add entries: "pack a turkey sandwich and an apple on Monday".

## Tasks

`/tasks` — the shared chore board. A task has a name, optional details, an optional assignee (either adult; blank = anyone), and a frequency (one-off, or every N days/weeks/months) with a next-due date. The list orders by due date — **Overdue** (red) and **Due today** (amber) float to the top, with header counts. **Done** in one click: a one-off archives; a recurring task rolls its due date forward *from the completion date* (doing a chore late doesn't pile it up), keeping its assignee. `/tasks/history` is the append-only who-did-what log. Due tasks also surface on the dashboard.

## Lessons

`/lessons` — parent-curated home learning for the kid (the kid never logs in). A **lesson** (title, optional subject/description, date window) contains ordered **objectives** (check off as done, optionally scheduled to a date), attached **resources** (label + link), and **exactly one test** — checking off the test is what completes the lesson.

## Projects

`/projects` — per-user personal project tracker (each adult sees their own). A **project** (name, status: idea/active/on hold/done/abandoned, optional goal and target date) has dated **milestones** (ordered, check-off; completing one auto-writes a journal line) and a dated **journal** of entries (note + optional link).

## Health

Grouped under one nav menu:

- **Exercise** (`/exercise`) — per-user log + household-shared catalog + weekly view. Catalog entries define each exercise once: body group (upper/lower/core/cardio), muscle-group tags, and a scoring type — `weighted` (`weight × reps × sets`), `distance` (`distance_km × body weight`), or `bodyweight_fraction` (`body weight × fraction × reps × sets`). The log form shows only the inputs the picked exercise needs; the work score is computed at save time and **persisted**, so later body-weight changes don't rewrite history. Body weight is per-user, set via the indicator at the top (required before logging distance/bodyweight exercises). `/exercise/weekly` totals the ISO week's score with a delta vs. last week and breakdowns by body group and muscle group. The assistant can log sessions by exercise name (unknown names error rather than auto-create).
- **Hikes** (`/hike`) — per-user, private Bruce Trail log: date, section, segment name, optional map links and times, distance, duration, notes; average speed computed and persisted. `/hike/progress` rolls up total distance / count / time and a per-section breakdown.
- **BP** (`/bp`) — per-user, private blood-pressure log: date, optional time, systolic/diastolic, optional heart rate, notes. MAP is computed and persisted; each reading gets a category badge (normal → crisis, descriptive only, not medical advice). `/bp/trends` shows averages, category distribution, and weekly breakdowns.

## Family

`/family` — non-login household members (kids). Name, notes, and school-day checkboxes — the school days drive the lunch-plan grid and dashboard counts. **Allergies and preferences don't go here — they go in Memory**, subject-tagged to the member. Setup order: add the kid, set school days, then capture restrictions in Memory.

## Memory

`/memory` — durable facts the assistant should apply across conversations. Each memory has a **subject** (`household`, `user`, or `family_member`), a **type** (`preference`, `food_preference`, `restriction`, `routine`, `planning_constraint`, `frequently_used`), free-text content, and optional tags (list-page filter only — not sent to the LLM).

**`is_hard_restriction`** — check for allergies and must-never-do rules. Creating, editing, or deleting one requires explicit confirmation everywhere (form checkbox, dedicated confirm page, assistant approval flow). The list pins hard restrictions on top; filters by subject, type, text, tag.

The LLM sees up to the 50 most recent memories on every assistant request — that's how "Alex is allergic to peanuts" persists across sessions.

## Tips

- The assistant is the fast path for **adding and asking**; the module pages are for everything else.
- Shared: grocery, meals + catalog, lunches, tasks, lessons, family, memory, exercise catalog. Per-user: exercise log, hikes, BP, projects, assistant history.
- Household-specific facts only reach the assistant if they're in Memory.
