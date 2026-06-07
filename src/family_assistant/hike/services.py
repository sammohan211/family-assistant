"""Hike CRUD + progress aggregation.

Exposes:
  - ``compute_speed`` (pure: km/h from distance + duration).
  - Per-user CRUD on ``Hike``, computing and persisting ``speed_kmh``.
  - ``progress`` summarising a user's hikes into overall totals plus a
    per-section breakdown (the Bruce Trail is walked section by section).
"""

from dataclasses import dataclass
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User
from family_assistant.hike.models import Hike


def compute_speed(distance_km: Decimal, duration_minutes: int) -> Decimal:
    """Average speed in km/h, rounded to three decimals. Zero duration -> 0."""
    if duration_minutes <= 0:
        return Decimal("0.000")
    raw = distance_km * Decimal(60) / Decimal(duration_minutes)
    return raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# CRUD (per-user)
# ---------------------------------------------------------------------------


def list_user_hikes(db: DbSession, *, user: User, limit: int = 500) -> list[Hike]:
    statement = (
        select(Hike)
        .where(Hike.user_id == user.id)
        .order_by(Hike.date.desc(), Hike.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_hike(db: DbSession, hike_id: int) -> Hike | None:
    return db.get(Hike, hike_id)


def create_hike(
    db: DbSession,
    *,
    user: User,
    entry_date: date,
    section: str,
    name: str,
    start_location: str | None,
    start_time: time | None,
    end_location: str | None,
    end_time: time | None,
    distance_km: Decimal,
    duration_minutes: int,
    notes: str | None,
) -> Hike:
    hike = Hike(
        user_id=user.id,
        date=entry_date,
        section=section.strip(),
        name=name.strip(),
        start_location=start_location.strip() if start_location else None,
        start_time=start_time,
        end_location=end_location.strip() if end_location else None,
        end_time=end_time,
        distance_km=distance_km,
        duration_minutes=duration_minutes,
        speed_kmh=compute_speed(distance_km, duration_minutes),
        notes=notes.strip() if notes else None,
    )
    db.add(hike)
    db.commit()
    db.refresh(hike)
    return hike


def update_hike(
    db: DbSession,
    *,
    hike_id: int,
    entry_date: date,
    section: str,
    name: str,
    start_location: str | None,
    start_time: time | None,
    end_location: str | None,
    end_time: time | None,
    distance_km: Decimal,
    duration_minutes: int,
    notes: str | None,
) -> Hike | None:
    hike = db.get(Hike, hike_id)
    if hike is None:
        return None
    hike.date = entry_date
    hike.section = section.strip()
    hike.name = name.strip()
    hike.start_location = start_location.strip() if start_location else None
    hike.start_time = start_time
    hike.end_location = end_location.strip() if end_location else None
    hike.end_time = end_time
    hike.distance_km = distance_km
    hike.duration_minutes = duration_minutes
    hike.speed_kmh = compute_speed(distance_km, duration_minutes)
    hike.notes = notes.strip() if notes else None
    db.commit()
    db.refresh(hike)
    return hike


def delete_hike(db: DbSession, hike_id: int) -> bool:
    hike = db.get(Hike, hike_id)
    if hike is None:
        return False
    db.delete(hike)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


@dataclass
class SectionTotal:
    section: str
    count: int
    distance_km: Decimal
    duration_minutes: int


@dataclass
class ProgressSummary:
    count: int
    total_distance_km: Decimal
    total_minutes: int
    avg_speed_kmh: Decimal | None
    by_section: list[SectionTotal]


def progress(db: DbSession, *, user: User) -> ProgressSummary:
    hikes = list_user_hikes(db, user=user, limit=1000)

    total_distance = sum((h.distance_km for h in hikes), Decimal("0"))
    total_minutes = sum(h.duration_minutes for h in hikes)
    avg_speed: Decimal | None = None
    if total_minutes > 0:
        avg_speed = (total_distance * Decimal(60) / Decimal(total_minutes)).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

    sections: dict[str, SectionTotal] = {}
    for h in hikes:
        st = sections.get(h.section)
        if st is None:
            sections[h.section] = SectionTotal(
                section=h.section,
                count=1,
                distance_km=h.distance_km,
                duration_minutes=h.duration_minutes,
            )
        else:
            st.count += 1
            st.distance_km += h.distance_km
            st.duration_minutes += h.duration_minutes

    by_section = sorted(sections.values(), key=lambda s: s.distance_km, reverse=True)

    return ProgressSummary(
        count=len(hikes),
        total_distance_km=total_distance,
        total_minutes=total_minutes,
        avg_speed_kmh=avg_speed,
        by_section=by_section,
    )
