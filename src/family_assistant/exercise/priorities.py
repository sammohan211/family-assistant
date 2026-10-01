"""Weekly training priorities for the dashboard card (PRD §10.16 step 3).

Code decides, the LLM phrases. The card (``training_card``) is rebuilt on
every dashboard view, without the LLM:

1. reads the weekly summaries (§10.16 step 2) for the last ``HISTORY_WEEKS``
   complete weeks plus the current week so far;
2. ranks body areas deterministically (``rank_areas``) — staleness, sets this
   week vs the user's own average (with a small floor), push/pull and
   upper/lower balance, cardio minutes vs average — and attaches candidate
   catalog exercises split into gym and home;
3. overlays this week's stored AI wording on the areas still ranked
   (``merge_card``); other areas keep the ranking's factual reason.

The LLM is called at most once per user per week, by Refresh
(``refresh_priorities``): it asks the LLM to pick 2-3 areas and phrase a
one-line reason, validates the answer against the ranking, the muscle
vocabulary and the catalog (``validate_answer``), and stores it in
``training_priorities``. Once a week has a stored AI answer, Refresh makes no
further calls; a failed call (``is_fallback``) may be retried.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.llm import LLMClient
from family_assistant.auth.models import User
from family_assistant.exercise.models import Exercise, ExerciseLog, TrainingPriorities
from family_assistant.exercise.services import list_exercises
from family_assistant.exercise.summary import get_week_summary, week_start
from family_assistant.exercise.taxonomy import MUSCLE_GROUPS, muscle_label

logger = logging.getLogger(__name__)

# Tunables. Kept here, not in settings: they shape advice, not deployment.
HISTORY_WEEKS = 4  # complete weeks averaged for "your usual"
SET_FLOOR = 4  # weekly sets a muscle is nudged toward even if you never train it
CARDIO_FLOOR = 60  # weekly cardio minutes nudged toward with no cardio history
STALE_CAP_DAYS = 14  # staleness saturates here; never-trained counts as this
BALANCE_RATIO = 0.75  # the weaker side of push/pull or upper/lower below this share
BALANCE_BONUS = 0.15
RECENT_PENALTY = 0.5  # trained today or yesterday: let it recover
# Never-trained muscles surface through the floor but shouldn't outrank a muscle
# you actually train and have let slip (else side delts would top every week).
NEVER_TRAINED_WEIGHT = 0.6
MIN_SCORE = 0.35  # areas below this are not worth a priority
MAX_PRIORITIES = 3
MAX_MUSCLES = 3
MAX_OPTIONS = 5  # candidate exercises per location
MAX_REASON_CHARS = 200

CARDIO = "Cardio"


class PrioritiesError(Exception):
    """Raised when there is nothing to rank (no recent logs)."""


# ---------------------------------------------------------------------------
# Deterministic ranking (pure)
# ---------------------------------------------------------------------------


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _muscle_scores(history: list[dict], current: dict) -> dict[str, dict[str, Any]]:
    """Per-muscle need for this week, 0 (done enough) upward."""
    weeks = [*history, current]
    group_totals = {group: sum(w["group_sets"][group] for w in weeks) for group in MUSCLE_GROUPS}
    weaker: set[str] = set()
    pairs = (
        (("Upper push",), ("Upper pull",)),
        (("Upper push", "Upper pull"), ("Lower",)),
    )
    for left, right in pairs:
        a = sum(group_totals[g] for g in left)
        b = sum(group_totals[g] for g in right)
        if max(a, b) > 0 and min(a, b) < BALANCE_RATIO * max(a, b):
            weaker.update(left if a < b else right)

    scores: dict[str, dict[str, Any]] = {}
    for group, muscles in MUSCLE_GROUPS.items():
        for muscle in muscles:
            usual = _avg([w["strength_sets"][muscle] for w in history])
            target = max(usual, SET_FLOOR)
            done = current["strength_sets"][muscle]
            need = max(target - done, 0) / target
            days = current["days_since_trained"][muscle]
            staleness = min(STALE_CAP_DAYS if days is None else days, STALE_CAP_DAYS)
            score = 0.0
            if need > 0:
                score = 0.5 * need + 0.5 * staleness / STALE_CAP_DAYS
                if group in weaker:
                    score += BALANCE_BONUS
                if days is None:
                    score *= NEVER_TRAINED_WEIGHT
                elif days <= 1:
                    score *= RECENT_PENALTY
            scores[muscle] = {
                "muscle": muscle,
                "group": group,
                "score": round(score, 3),
                "sets_this_week": done,
                "usual_sets": round(usual, 1),
                "days_since_trained": days,
            }
    return scores


def _muscle_reason(m: dict[str, Any]) -> str:
    days = m["days_since_trained"]
    when = "never trained" if days is None else f"last trained {days} days ago"
    if days == 0:
        when = "trained today"
    elif days == 1:
        when = "trained yesterday"
    target = max(m["usual_sets"], SET_FLOOR)
    return (
        f"{muscle_label(m['muscle'])}: {when}; "
        f"{_fmt(m['sets_this_week'])} of ~{_fmt(target)} sets this week."
    )


def _options(
    exercises: list[Exercise], need: dict[str, float], modality: str
) -> dict[str, list[str]]:
    """Catalog exercises for these muscles, best match first, split by location.

    ``need`` maps each chosen muscle to its score. An exercise earns the score of
    each needed muscle it trains (in full as primary, half as secondary), so a
    row that hits the lead muscle outranks a curl that only touches a minor one.
    """
    ranked = []
    for exercise in exercises:
        if exercise.modality != modality:
            continue
        if modality == "cardio":
            ranked.append((0.0, exercise.name, exercise))
            continue
        fit = sum(need.get(m, 0) for m in exercise.primary_muscles) + 0.5 * sum(
            need.get(m, 0) for m in exercise.secondary_muscles
        )
        if fit > 0:
            ranked.append((-fit, exercise.name, exercise))
    ranked.sort(key=lambda row: row[:2])
    gym = [e.name for _, _, e in ranked if e.location in ("gym", "both")]
    home = [e.name for _, _, e in ranked if e.location in ("home", "both")]
    return {"gym": gym[:MAX_OPTIONS], "home": home[:MAX_OPTIONS]}


def rank_areas(
    history: list[dict], current: dict, exercises: list[Exercise]
) -> list[dict[str, Any]]:
    """Body areas worth prioritizing this week, most needed first.

    ``history`` holds the complete weeks' summaries, ``current`` the partial
    week's. Each area carries its top muscles, a factual reason, and candidate
    gym/home exercises from the catalog. Pure: no DB access.
    """
    scores = _muscle_scores(history, current)
    areas = []
    for group, muscles in MUSCLE_GROUPS.items():
        needed = sorted(
            (scores[m] for m in muscles if scores[m]["score"] > 0),
            key=lambda m: (-m["score"], m["muscle"]),
        )
        if not needed:
            continue
        top = needed[0]["score"]
        chosen = [m for m in needed if m["score"] >= 0.6 * top][:MAX_MUSCLES]
        names = [m["muscle"] for m in chosen]
        areas.append(
            {
                "area": group,
                "score": top,
                "muscles": names,
                "detail": chosen,
                "reason": _muscle_reason(chosen[0]),
                **_options(exercises, {m["muscle"]: m["score"] for m in chosen}, "strength"),
            }
        )

    usual_cardio = _avg([w["cardio_minutes"]["total"] for w in history])
    target = max(usual_cardio, CARDIO_FLOOR)
    done = current["cardio_minutes"]["total"]
    need = max(target - done, 0) / target
    if need > 0:
        areas.append(
            {
                "area": CARDIO,
                "score": round(0.8 * need, 3),
                "muscles": [],
                "detail": [],
                "reason": f"{done} of ~{round(target)} cardio minutes this week.",
                **_options(exercises, {}, "cardio"),
            }
        )

    areas = [a for a in areas if a["score"] >= MIN_SCORE and (a["gym"] or a["home"])]
    areas.sort(key=lambda a: (-a["score"], a["area"]))
    return areas[:MAX_PRIORITIES]


def _wins(current: dict) -> list[str]:
    return [
        row["exercise"]
        for row in current["progress"]
        if row["change_pct"] is not None and row["change_pct"] >= 0
    ]


def keep_it_up(current: dict) -> str | None:
    """Exercises this week that met or beat their last session's score."""
    wins = _wins(current)
    if not wins:
        return None
    return "Matched or beat your last score on " + ", ".join(wins) + "."


def fallback_content(areas: list[dict[str, Any]], current: dict) -> dict[str, Any]:
    """The card's content straight from the ranking (no LLM)."""
    return {
        "priorities": [
            {
                "area": a["area"],
                "muscles": a["muscles"],
                "reason": a["reason"],
                "gym": a["gym"],
                "home": a["home"],
            }
            for a in areas
        ],
        "keep_it_up": keep_it_up(current),
    }


# ---------------------------------------------------------------------------
# LLM prompt + validation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a friendly training coach inside a family app. The user is not a
bodybuilder: they train at a gym, at home (dumbbells, push-ups, sit-ups, a
rowing machine) and on hikes, and only want gentle weekly hints.

You receive JSON with this week's candidate priorities, already ranked by code
(most needed first), each with its muscles, facts and candidate exercises for
the gym and for home. Choose 2 or 3 of the candidates (fewer if fewer are
given) and write one short, encouraging reason for each, grounded in the facts.
For each, pick up to 3 gym options and up to 3 home options, ONLY from that
candidate's own lists (ordered best match first; prefer earlier ones), copying
names exactly. Use only the muscles listed for
that candidate. Do not invent exercises, muscles, numbers or medical advice.
If "wins" is not empty, add one short "keep_it_up" line praising them;
otherwise set it to null.

Reply with JSON only:
{"priorities": [{"area": "<candidate area>", "muscles": ["<muscle id>"],
  "reason": "<one sentence>", "gym": ["<name>"], "home": ["<name>"]}],
 "keep_it_up": "<one sentence>" | null}
"""


def build_messages(
    areas: list[dict[str, Any]], history: list[dict], current: dict
) -> list[dict[str, str]]:
    payload = {
        "today": current["as_of"],
        "candidates": [
            {
                "area": a["area"],
                "muscles": [
                    {
                        "id": m["muscle"],
                        "name": muscle_label(m["muscle"]),
                        "sets_this_week": m["sets_this_week"],
                        "usual_sets_per_week": m["usual_sets"],
                        "days_since_trained": m["days_since_trained"],
                    }
                    for m in a["detail"]
                ],
                "facts": a["reason"],
                "gym": a["gym"],
                "home": a["home"],
            }
            for a in areas
        ],
        "recent_weeks": [
            {
                "week_start": w["week_start"],
                "sets_by_area": w["group_sets"],
                "cardio_minutes": w["cardio_minutes"]["total"],
                "active_days": w["active_days"],
            }
            for w in [*history, current]
        ],
        "wins": _wins(current),
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


class _Priority(BaseModel):
    area: str
    muscles: list[str] = []
    reason: str = ""
    gym: list[str] = []
    home: list[str] = []


class _Answer(BaseModel):
    priorities: list[_Priority]
    keep_it_up: str | None = None


def validate_answer(raw: Any, areas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Keep only what the ranking allows; ``None`` if nothing usable remains.

    Each priority must name a ranked area; its muscles and exercises are
    filtered to that area's own muscles and candidates (matched ignoring case,
    stored with the catalog's spelling). A missing reason falls back to the
    ranking's factual one.
    """
    try:
        answer = _Answer.model_validate(raw)
    except ValidationError:
        return None

    by_area = {a["area"].lower(): a for a in areas}
    seen: set[str] = set()
    priorities = []
    for p in answer.priorities:
        area = by_area.get(p.area.strip().lower())
        if area is None or area["area"] in seen:
            continue
        seen.add(area["area"])

        def pick(names: list[str], allowed: list[str]) -> list[str]:
            canonical = {n.lower(): n for n in allowed}
            out: list[str] = []
            for name in names:
                match = canonical.get(str(name).strip().lower())
                if match and match not in out:
                    out.append(match)
            return out[:MAX_OPTIONS]

        gym = pick(p.gym, area["gym"])
        home = pick(p.home, area["home"])
        if not gym and not home:
            continue
        muscles = pick(p.muscles, area["muscles"]) or area["muscles"]
        reason = " ".join(p.reason.split())[:MAX_REASON_CHARS] or area["reason"]
        priorities.append(
            {"area": area["area"], "muscles": muscles, "reason": reason, "gym": gym, "home": home}
        )
        if len(priorities) == MAX_PRIORITIES:
            break

    if not priorities:
        return None
    note = " ".join((answer.keep_it_up or "").split())[:MAX_REASON_CHARS] or None
    return {"priorities": priorities, "keep_it_up": note}


# ---------------------------------------------------------------------------
# Refresh + storage
# ---------------------------------------------------------------------------


def has_recent_logs(db: DbSession, *, user: User, today: date | None = None) -> bool:
    """The card is shown only to users who logged something in the last 4 weeks."""
    today = today or date.today()
    since = today - timedelta(days=7 * HISTORY_WEEKS)
    return bool(
        db.scalar(select(exists().where(ExerciseLog.user_id == user.id, ExerciseLog.date >= since)))
    )


def get_priorities(
    db: DbSession, *, user: User, today: date | None = None
) -> TrainingPriorities | None:
    """This week's stored AI answer (or failed attempt), if Refresh has been pressed."""
    start = week_start(today or date.today())
    return db.scalars(
        select(TrainingPriorities).where(
            TrainingPriorities.user_id == user.id, TrainingPriorities.week_start == start
        )
    ).first()


def ai_used(row: TrainingPriorities | None) -> bool:
    """True once this week's LLM call has produced a usable answer."""
    return row is not None and row.model is not None and not row.is_fallback


def _rank(
    db: DbSession, *, user: User, today: date
) -> tuple[list[dict], dict, list[dict[str, Any]]]:
    start = week_start(today)
    history = [
        get_week_summary(db, user=user, start=start - timedelta(days=7 * n), today=today)
        for n in range(HISTORY_WEEKS, 0, -1)
    ]
    current = get_week_summary(db, user=user, start=start, today=today)
    return history, current, rank_areas(history, current, list_exercises(db))


def merge_card(
    areas: list[dict[str, Any]], current: dict, row: TrainingPriorities | None
) -> dict[str, Any]:
    """The card for the current ranking, worded by the stored AI answer where it still fits.

    The AI answer is re-validated against today's ranking, so an area the user
    has since trained drops out and a newly ranked one shows its factual reason.
    The AI's "keep it up" line is kept only while the wins it praised are unchanged.
    """
    content = fallback_content(areas, current)
    content["as_of"] = current["as_of"]
    if not ai_used(row):
        return content
    worded = validate_answer(row.content, areas)
    if worded is not None:
        by_area = {p["area"]: p for p in worded["priorities"]}
        content["priorities"] = [by_area.get(p["area"], p) for p in content["priorities"]]
        if row.content.get("wins") == _wins(current):
            content["keep_it_up"] = worded["keep_it_up"]
    return content


def training_card(db: DbSession, *, user: User, today: date | None = None) -> dict[str, Any]:
    """Everything the dashboard card shows. Never calls the LLM."""
    today = today or date.today()
    _, current, areas = _rank(db, user=user, today=today)
    row = get_priorities(db, user=user, today=today)
    return {
        "content": merge_card(areas, current, row),
        "ai_used": ai_used(row),
        "ai_at": row.generated_at if ai_used(row) else None,
        "ai_failed": row is not None and row.is_fallback,
    }


def refresh_priorities(
    db: DbSession,
    *,
    user: User,
    llm: LLMClient,
    model_label: str | None,
    today: date | None = None,
) -> TrainingPriorities | None:
    """Ask the LLM to word this week's priorities, at most once per week.

    Returns the week's row, unchanged when the LLM has already answered this
    week, or ``None`` when nothing ranks (no call is needed to say "on track").
    """
    today = today or date.today()
    if not has_recent_logs(db, user=user, today=today):
        raise PrioritiesError("Log some exercise first — there is nothing recent to go on.")

    row = get_priorities(db, user=user, today=today)
    if ai_used(row):
        return row
    history, current, areas = _rank(db, user=user, today=today)
    if not areas:
        return row

    content: dict[str, Any] | None = None
    try:
        raw = llm.chat_json(build_messages(areas, history, current))
    except Exception:  # httpx errors, JSON decode: fall back, never fail the card
        logger.warning("training priorities LLM call failed", exc_info=True)
    else:
        content = validate_answer(raw, areas)
    is_fallback = content is None
    if content is None:
        content = fallback_content(areas, current)
    content["as_of"] = current["as_of"]
    content["wins"] = _wins(current)
    model = None if is_fallback else model_label

    if row is None:
        row = TrainingPriorities(user_id=user.id, week_start=week_start(today))
        db.add(row)
    row.content, row.model, row.is_fallback = content, model, is_fallback
    try:
        db.commit()
    except IntegrityError:  # a concurrent first refresh won; overwrite it
        db.rollback()
        row = get_priorities(db, user=user, today=today)
        row.content, row.model, row.is_fallback = content, model, is_fallback
        db.commit()
    return row


class CannedPrioritiesLLM:
    """Offline stand-in (USE_MOCK_LLM=true): echoes the top candidates."""

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = json.loads(messages[-1]["content"])
        return {
            "priorities": [
                {
                    "area": c["area"],
                    "muscles": [m["id"] for m in c["muscles"]],
                    "reason": f"{c['facts']} (Offline mode — no model was consulted.)",
                    "gym": c["gym"][:3],
                    "home": c["home"][:3],
                }
                for c in payload["candidates"][:MAX_PRIORITIES]
            ],
            "keep_it_up": None,
        }
