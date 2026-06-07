"""Blood pressure CRUD + classification + trend aggregation.

Exposes:
  - ``mean_arterial_pressure`` and ``classify`` (pure helpers).
  - Per-user CRUD on ``BloodPressureReading``, computing and persisting
    ``map_value`` on every create/update.
  - ``trends`` aggregating a user's readings into overall averages plus a
    per-ISO-week breakdown (newest first), reusing the same week-start
    convention as the exercise weekly view.
"""

from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User
from family_assistant.bp.models import BloodPressureReading

# American Heart Association blood-pressure categories, checked most-severe first.
# Each tuple is (label, css_tone) where css_tone keys the badge colour in the UI.
CATEGORIES = (
    ("Hypertensive crisis", "crisis"),
    ("Stage 2", "stage2"),
    ("Stage 1", "stage1"),
    ("Elevated", "elevated"),
    ("Normal", "normal"),
)


def mean_arterial_pressure(systolic: int, diastolic: int) -> Decimal:
    """MAP = (SBP + 2·DBP) / 3, rounded to two decimals."""
    raw = Decimal(systolic + 2 * diastolic) / Decimal(3)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def classify(systolic: int, diastolic: int) -> tuple[str, str]:
    """Return (label, tone) for a reading per AHA thresholds."""
    if systolic > 180 or diastolic > 120:
        return CATEGORIES[0]
    if systolic >= 140 or diastolic >= 90:
        return CATEGORIES[1]
    if systolic >= 130 or diastolic >= 80:
        return CATEGORIES[2]
    if systolic >= 120:  # diastolic < 80 here, else caught above
        return CATEGORIES[3]
    return CATEGORIES[4]


# ---------------------------------------------------------------------------
# CRUD (per-user)
# ---------------------------------------------------------------------------


def list_user_readings(
    db: DbSession, *, user: User, limit: int = 200
) -> list[BloodPressureReading]:
    statement = (
        select(BloodPressureReading)
        .where(BloodPressureReading.user_id == user.id)
        .order_by(
            BloodPressureReading.date.desc(),
            BloodPressureReading.reading_time.desc().nullslast(),
            BloodPressureReading.id.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_reading(db: DbSession, reading_id: int) -> BloodPressureReading | None:
    return db.get(BloodPressureReading, reading_id)


def create_reading(
    db: DbSession,
    *,
    user: User,
    entry_date: date,
    reading_time: time | None,
    systolic: int,
    diastolic: int,
    heart_rate: int | None,
    notes: str | None,
) -> BloodPressureReading:
    reading = BloodPressureReading(
        user_id=user.id,
        date=entry_date,
        reading_time=reading_time,
        systolic=systolic,
        diastolic=diastolic,
        heart_rate=heart_rate,
        map_value=mean_arterial_pressure(systolic, diastolic),
        notes=notes.strip() if notes else None,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def update_reading(
    db: DbSession,
    *,
    reading_id: int,
    entry_date: date,
    reading_time: time | None,
    systolic: int,
    diastolic: int,
    heart_rate: int | None,
    notes: str | None,
) -> BloodPressureReading | None:
    reading = db.get(BloodPressureReading, reading_id)
    if reading is None:
        return None
    reading.date = entry_date
    reading.reading_time = reading_time
    reading.systolic = systolic
    reading.diastolic = diastolic
    reading.heart_rate = heart_rate
    reading.map_value = mean_arterial_pressure(systolic, diastolic)
    reading.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(reading)
    return reading


def delete_reading(db: DbSession, reading_id: int) -> bool:
    reading = db.get(BloodPressureReading, reading_id)
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
class WeeklyVitals:
    week_start: date
    count: int
    avg_systolic: Decimal | None
    avg_diastolic: Decimal | None
    avg_heart_rate: Decimal | None


@dataclass
class TrendSummary:
    count: int
    avg_systolic: Decimal | None
    avg_diastolic: Decimal | None
    avg_heart_rate: Decimal | None
    latest: BloodPressureReading | None
    category_counts: list[tuple[str, str, int]]  # (label, tone, count)
    weekly: list[WeeklyVitals]


def trends(db: DbSession, *, user: User, weeks: int = 12) -> TrendSummary:
    readings = list_user_readings(db, user=user, limit=1000)

    counts: dict[str, int] = {label: 0 for label, _ in CATEGORIES}
    by_week: dict[date, list[BloodPressureReading]] = {}
    for r in readings:
        label, _ = classify(r.systolic, r.diastolic)
        counts[label] += 1
        by_week.setdefault(week_start(r.date), []).append(r)

    weekly = [
        WeeklyVitals(
            week_start=ws,
            count=len(group),
            avg_systolic=_avg([r.systolic for r in group]),
            avg_diastolic=_avg([r.diastolic for r in group]),
            avg_heart_rate=_avg([r.heart_rate for r in group if r.heart_rate is not None]),
        )
        for ws, group in sorted(by_week.items(), reverse=True)[:weeks]
    ]

    return TrendSummary(
        count=len(readings),
        avg_systolic=_avg([r.systolic for r in readings]),
        avg_diastolic=_avg([r.diastolic for r in readings]),
        avg_heart_rate=_avg([r.heart_rate for r in readings if r.heart_rate is not None]),
        latest=readings[0] if readings else None,
        category_counts=[
            (label, tone, counts[label]) for label, tone in CATEGORIES if counts[label] > 0
        ],
        weekly=weekly,
    )
