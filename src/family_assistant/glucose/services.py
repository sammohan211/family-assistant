"""Blood glucose CRUD + classification + trend aggregation.

Exposes:
  - ``classify`` (pure helper) — **context-aware**, unlike BP's single fixed
    scale: fasting and post-meal readings have genuinely different normal
    ranges, so one scale would mislead.
  - Per-user CRUD on ``GlucoseReading``, mirroring the BP module's shape.
  - ``trends`` aggregating a user's readings into overall averages, per-context
    averages, category distribution, a per-ISO-week breakdown, and a flat
    ``chart_points`` list the trends template feeds straight to Chart.js.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User
from family_assistant.glucose.models import GlucoseReading

CONTEXTS = ("fasting", "after_meal", "random")

CONTEXT_LABELS = {
    "fasting": "Fasting",
    "after_meal": "After meal",
    "random": "Random",
}

# Shown under the context choice in the log form so picking one is unambiguous.
CONTEXT_HELP = {
    "fasting": "No food or drink (except water) for 8+ hours, typically first thing in the morning",
    "after_meal": "About 2 hours after starting a meal",
    "random": "Any other time — spot-check, bedtime, etc.",
}

# (label, tone) tuples, most-severe first.
_CATEGORIES = (
    ("High", "high"),
    ("Elevated", "elevated"),
    ("Normal", "normal"),
)


def classify(value_mg_dl: int, context: str) -> tuple[str, str]:
    """Return (label, tone) for a reading. Thresholds depend on context:

    fasting: normal <100, elevated 100-125, high 126+.
    after_meal / random: normal <140, elevated 140-199, high 200+ (random
    borrows the after-meal scale — the standard reference range for an
    unqualified "random glucose" reading).
    """
    if context == "fasting":
        if value_mg_dl >= 126:
            return _CATEGORIES[0]
        if value_mg_dl >= 100:
            return _CATEGORIES[1]
        return _CATEGORIES[2]
    if value_mg_dl >= 200:
        return _CATEGORIES[0]
    if value_mg_dl >= 140:
        return _CATEGORIES[1]
    return _CATEGORIES[2]


# ---------------------------------------------------------------------------
# CRUD (per-user)
# ---------------------------------------------------------------------------


def list_user_readings(db: DbSession, *, user: User, limit: int = 200) -> list[GlucoseReading]:
    statement = (
        select(GlucoseReading)
        .where(GlucoseReading.user_id == user.id)
        .order_by(
            GlucoseReading.date.desc(),
            GlucoseReading.reading_time.desc().nullslast(),
            GlucoseReading.id.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_reading(db: DbSession, reading_id: int) -> GlucoseReading | None:
    return db.get(GlucoseReading, reading_id)


def create_reading(db, *, user, entry_date, reading_time, value_mg_dl, context, notes):
    reading = GlucoseReading(
        user_id=user.id,
        date=entry_date,
        reading_time=reading_time,
        value_mg_dl=value_mg_dl,
        context=context,
        notes=notes.strip() if notes else None,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def update_reading(db, *, reading_id, entry_date, reading_time, value_mg_dl, context, notes):
    reading = db.get(GlucoseReading, reading_id)
    if reading is None:
        return None
    reading.date = entry_date
    reading.reading_time = reading_time
    reading.value_mg_dl = value_mg_dl
    reading.context = context
    reading.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(reading)
    return reading


def delete_reading(db: DbSession, reading_id: int) -> bool:
    reading = db.get(GlucoseReading, reading_id)
    if reading is None:
        return False
    db.delete(reading)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def week_start(reference: date) -> date:
    """Monday of the ISO week containing ``reference``."""
    return reference - timedelta(days=reference.weekday())


def _avg(values: list[int]) -> Decimal | None:
    if not values:
        return None
    raw = Decimal(sum(values)) / Decimal(len(values))
    return raw.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class WeeklyGlucose:
    week_start: date
    count: int
    avg_value: Decimal | None


@dataclass
class ContextAverage:
    context: str
    label: str
    avg_value: Decimal | None
    count: int


@dataclass
class TrendSummary:
    count: int
    avg_value: Decimal | None
    latest: GlucoseReading | None
    category_counts: list[tuple[str, str, int]]  # (label, tone, count)
    context_averages: list[ContextAverage]
    weekly: list[WeeklyGlucose]
    chart_points: list[dict]  # oldest first, for Chart.js


def trends(db: DbSession, *, user: User, weeks: int = 12) -> TrendSummary:
    readings = list_user_readings(db, user=user, limit=1000)

    tone_counts: dict[str, int] = {}
    label_by_tone: dict[str, str] = {}
    by_week: dict[date, list[GlucoseReading]] = {}
    by_context: dict[str, list[GlucoseReading]] = {c: [] for c in CONTEXTS}

    for r in readings:
        label, tone = classify(r.value_mg_dl, r.context)
        tone_counts[tone] = tone_counts.get(tone, 0) + 1
        label_by_tone[tone] = label
        by_week.setdefault(week_start(r.date), []).append(r)
        by_context.setdefault(r.context, []).append(r)

    weekly = [
        WeeklyGlucose(
            week_start=ws,
            count=len(group),
            avg_value=_avg([r.value_mg_dl for r in group]),
        )
        for ws, group in sorted(by_week.items(), reverse=True)[:weeks]
    ]

    context_averages = [
        ContextAverage(
            context=c,
            label=CONTEXT_LABELS[c],
            avg_value=_avg([r.value_mg_dl for r in group]),
            count=len(group),
        )
        for c, group in by_context.items()
    ]

    ordered_tones = ("high", "elevated", "normal")
    category_counts = [
        (label_by_tone[t], t, tone_counts[t]) for t in ordered_tones if tone_counts.get(t)
    ]

    chart_points = [
        {
            "date": r.date.isoformat(),
            "time": r.reading_time.strftime("%H:%M") if r.reading_time else None,
            "value": r.value_mg_dl,
            "context": r.context,
            "notes": r.notes or "",
        }
        for r in reversed(readings)
    ]

    return TrendSummary(
        count=len(readings),
        avg_value=_avg([r.value_mg_dl for r in readings]),
        latest=readings[0] if readings else None,
        category_counts=category_counts,
        context_averages=context_averages,
        weekly=weekly,
        chart_points=chart_points,
    )
