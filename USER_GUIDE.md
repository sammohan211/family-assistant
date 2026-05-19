# User Guide

How to use the Family Assistant app once it's running. For installing the stack see `DESKTOP_SETUP.md`; for keeping it running (logs, backups, model switching) see `OPERATIONS.md`.

The app has nine pages, reachable from the top nav: **Dashboard, Assistant, Grocery, Meal plan, Lunch plan, Exercise, Family, Memory** (plus Login).

---

## Logging in

`USER1_*` and `USER2_*` in `.env` define the accounts. Email + plaintext password on the login page; the password is checked against the Argon2id hash you stored.

If you forget the password: it's not recoverable — generate a new hash, replace `USERn_PASSWORD_HASH` in `.env`, `docker compose restart app`, log in with the new plaintext.

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
- `exercise.log_activity` — log an exercise for you.
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

`/grocery` — household shopping list.

**Add an item:** "New item" button → name (required), optional quantity, unit, category, notes. Quantity is free-text but numeric is preferred ("2", "1.5").

**Per-item actions** on the list:
- **Purchase** — moves the item to the purchased section (history kept).
- **Restore** — un-purchase, back to open.
- **Clone** — duplicate (handy for recurring buys: clone last week's "milk").
- **Edit / Delete** — straightforward.

The dashboard's quick-add box creates an item with only a name — open the grocery page if you need quantity or category.

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

`/exercise` — log workouts for yourself (the logged-in user).

**Add an entry:** activity (free text, e.g. "Running", "Yoga"), duration in minutes, date, optional notes. Each user only sees their own log.

There are no aggregations yet (weekly totals, streaks) — it's a plain log.

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
- **Each user's exercise log is private**; everything else (grocery, meals, lunches, family, memory) is shared across both users in the household.
