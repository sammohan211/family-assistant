# User Guide

How to use the Family Assistant app once it's running. For installing the stack see `DESKTOP_SETUP.md`; for keeping it running (logs, backups, model switching) see `OPERATIONS.md`.

The app has nine pages, reachable from the top nav: **Dashboard, Assistant, Grocery, Meal plan, Lunch plan, Exercise, Family, Memory** (plus Login).

---

## Logging in

The app supports exactly two login users — set both `USER1_*` and `USER2_*` in `.env`. Email + password on the login page; checked against the Argon2id hash in `.env`. Sessions last 30 days; the **Log out** link in the top nav ends them.

If you forget the password: it's not recoverable — generate a new hash (see `OPERATIONS.md` → Users for the `argon2` one-liner), replace `USERn_PASSWORD_HASH` in `.env`, `docker compose restart app`, log in with the new password.

---

## Dashboard

`/dashboard` — the landing page. Four cards:

- **Today's meals** — meal plan entries whose `date` is today, grouped by type.
- **School lunches this week** — per family member, count of planned vs. packed lunches for the current week.
- **Grocery** — quick-add box (just a name; for quantity/unit/notes use the full grocery page) plus the first 5 open items.
- **Recent assistant activity** — your last few assistant prompts and their status.

This is also the page to come back to first thing in the morning — it answers "what's already planned for today?"

---

## Assistant

`/assistant` — type a request in plain English. The LLM decides whether to (a) just reply, (b) act immediately on a low-risk action, or (c) propose actions and wait for your confirmation.

**What it can do** (the tools it has access to):

- `grocery.add_items` — add items to the grocery list.
- `grocery.mark_purchased` — mark items as purchased.
- `meal_plan.create_entry` — schedule a meal on a date.
- `lunch_plan.create_entry` — plan a school lunch for one family member on a date.
- `exercise.log_activity` — log one session against a catalog exercise (referenced by name). Unknown names return an error — add to the catalog first.
- `memory.create` — save a household / user / family-member preference or restriction.
- `memory.search` — look up existing memories.

It does **not** currently update, delete, or rename via the assistant — use the module pages for that.

**When it asks to confirm:**

- More than 3 actions in one request.
- Adding/marking more than 3 grocery items in one go.
- Creating a "hard restriction" memory (e.g. allergies).

Other actions execute immediately. The "Did:" list below the response shows what actually happened (✓ row IDs, or ⚠ + error). Pending actions show as a yellow box with Approve / Cancel buttons.

**Examples that work well:**

```
Add milk, bread, and eggs to the grocery list.
Plan tacos for dinner this Friday.
What's on the grocery list?
Pack a sandwich and an apple for Maya's lunch on Monday.
Remember Alex is allergic to peanuts.
I ran 5k this morning.
```

**If you see no reply at all**: model isn't loaded — check `docker compose logs ollama` and `OPERATIONS.md` → Common issues.

---

## Grocery

`/grocery` — household shopping list. Shared across both users.

**Add an item:** "New item" button → name (required), optional quantity, unit, category, notes. Quantity accepts decimals (`2`, `1.5`, `0.25`) up to 3 fractional digits, or blank. Unit is free-form text (`lb`, `cartons`, `dozen` — anything); it's displayed next to the quantity but isn't normalised or used for math.

**Per-item actions** on the list:
- **Purchase** — moves the item to the purchased section (history kept).
- **Restore** — un-purchase, back to open.
- **Clone** — duplicate (handy for recurring buys: clone last week's "milk").
- **Edit / Delete** — straightforward.

The dashboard's quick-add box creates an item with only a name — open the grocery page if you need quantity or category.

**The list is a scratchpad, not stock tracking.** There's no deduplication: if you add `eggs · 1 dozen` and someone else adds `eggs · 30` later (via the form or the assistant), you get two separate rows — the system doesn't notice or merge. Whoever shops reconciles by eye. Unit strings are never compared, so `"dozen"`, `"items"`, and `""` are treated as three different units. Keep names simple and consistent if you want fewer duplicates.

---

## Meal plan

`/meal-plan` — what you're cooking, when.

**Add an entry:** title (e.g. "Tacos"), date, meal type (`breakfast`, `lunch`, `dinner`, `snack`), optional notes, optional "favorite" flag.

**Favorites** are just a checkbox on each entry — useful to mark dishes you'd want to repeat later. There's no auto-recurrence; use **Duplicate** to copy an entry to a new date.

The list is ordered by date. Past entries stay visible as a record of what you actually cooked.

---

## Lunch plan

`/lunch-plan` — school lunches per family member per day. Different from meal plan because it's per-person and tracks a packed/planned status.

**Add an entry:** pick a family member, a date, write the lunch contents in the **Items** textarea (one item per line — e.g. "sandwich\napple\nyogurt"), optional notes, status (`planned` or `packed`).

**Per-entry actions:**
- **Mark packed / Mark planned** — toggles status without opening the form.
- **Edit / Delete**.

Family members need their `school_days` set (in the family page) for the dashboard's weekly count to make sense.

---

## Exercise

Three pages, reachable from the tab bar at the top of any exercise screen:

- **Log** (`/exercise`) — your workout history.
- **Catalog** (`/exercise/catalog`) — household-shared list of named exercises (Bench press, Run, etc.) with their classification.
- **Weekly** (`/exercise/weekly`) — aggregated work-score totals for the current ISO week with a delta vs. the previous week.

Every page has a **Body weight** indicator at the top (collapsed by default — click to expand and edit). This value is per-user and feeds into score formulas for distance and bodyweight-fraction exercises. Set it once; update when it changes.

### Catalog (household-shared)

The catalog is where you define each exercise once. Logs reference catalog entries by name. Catalog is empty by default — populate as you go.

Each exercise has:

- **Name** (unique across the household).
- **Body group** — one of `upper`, `lower`, `core`, `cardio`. Used by the weekly view.
- **Muscle groups** — comma-separated tags (e.g. `chest, triceps, shoulders`). Used by the weekly view; free-form for now.
- **Scoring type** — picks the formula used to compute a session's work score:
  - `weighted` → `weight × reps × sets` (e.g. bench press, squat).
  - `distance` → `distance_km × your body weight` (e.g. run, hike, rowing machine, walk).
  - `bodyweight_fraction` → `body_weight × fraction × reps × sets` (e.g. captain's chair, dips, pull-ups).
- **Bodyweight fraction** — decimal (default `1.000`). Only matters when scoring type is `bodyweight_fraction`. Examples: pull-ups = `1.0`, captain's chair = `0.5`.

Add a few exercises before you start logging — the log form needs at least one to pick from.

### Log

The log form shows only the inputs the picked exercise's scoring type needs:

- Pick `Bench press (weighted)` → form asks for **sets, reps, weight**.
- Pick `Run (distance)` → form asks for **distance (km)**.
- Pick `Captain's chair (bodyweight_fraction)` → form asks for **sets, reps**.

**Duration** (minutes) and **notes** are optional on any log.

On save, the app computes the work score from the formula and **persists it on the row** — so if you later update your body weight, old scores don't change. Each session stays comparable to the day it was logged.

If you try to log a `distance` or `bodyweight_fraction` exercise without setting your body weight first, you'll get a clear error: set it via the indicator at the top.

The log list shows your sessions newest-first with the score on each row. Edit and Delete are per-entry.

### Weekly view

`/exercise/weekly` is the answer to "did I beat last week?":

- **Total work score** for the current ISO week (Monday–Sunday).
- **Delta vs. prior week** — absolute and percent, green if you improved, red if not.
- **By body group** — bar chart of how much score came from `upper`, `lower`, `core`, `cardio`. Quick way to spot under-trained areas.
- **By muscle group** — same idea, sorted descending. Uses the tags you put on each catalog exercise.

Use the **Prev / Next / This week** buttons to walk other weeks.

Per-exercise breakdown within a body group ("which exercise drove most of upper-body this week?") is not in MVP — it's on the phase 2 list.

---

## Family

`/family` — people in the household other than `USER1`/`USER2`. Children typically. Used by the lunch plan and memory pages.

**Add a member:** name, optional notes, school-day checkboxes (Mon–Sun). The school-day selection feeds the dashboard's "lunches this week" totals (only counts days they go to school).

---

## Memory

`/memory` — durable preferences, restrictions, and routines that the assistant should remember across conversations.

**Add a memory:** pick a **subject**:
- `household` — applies to everyone.
- `user` — pick one of the login users.
- `family_member` — pick one family member.

Then pick a **type**:
- `preference` — soft "likes" ("prefers oat milk").
- `food_preference` — food-specific likes/dislikes.
- `restriction` — must-avoid that isn't life-threatening ("vegetarian on Fridays").
- `routine` — recurring patterns ("swim practice Tuesdays").
- `planning_constraint` — scheduling rules ("no dentist before 9am").
- `frequently_used` — items/dishes/activities used often.

**Content** = the actual memory text. **Tags** are comma-separated and optional.

**`is_hard_restriction`** — check this for allergies and any "must never do" rules. The form requires a second confirmation checkbox before saving, because the assistant treats these specially (creating one via the assistant always asks for confirmation first).

Memories are surfaced to the LLM as context on every assistant request — that's how it remembers "Alex is allergic to peanuts" across sessions.

---

## Tips

- **The assistant is the fast path** for adding things ("add X to grocery", "plan tacos Friday"). The module pages are the fast path for editing, deleting, and viewing.
- **The dashboard is the morning glance** — meals today, lunches this week, what's on the grocery list, recent assistant activity. If nothing surprises you, you're set.
- **Hard restrictions and allergies belong in Memory**, not just in your head — the assistant only knows what's stored.
- **Exercise**: each user sees their own log; the catalog is shared; body weight is per user. Grocery, meals, lunches, family, and memory are shared across both users.
