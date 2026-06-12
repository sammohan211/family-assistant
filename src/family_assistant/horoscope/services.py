"""Horoscope period resolution, fact computation, and lazy generate-and-cache.

The flow (PRD §21 Phase 4): a period token (``today`` … ``next-year``) maps to
a stable cache key; on reveal we compute that period's transit facts in code
(astro.py) against the precomputed natal facts, ask the LLM to write one
reading per system grounded in those facts, and store the three rows. Cached
periods are served straight from the table — no background generation ever.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from family_assistant.ai_gateway.llm import LLMClient
from family_assistant.horoscope import astro
from family_assistant.horoscope.models import HoroscopeReading

SYSTEMS = ("vedic", "chinese", "western")

# Token → label, in display order. Tokens are URL path segments.
PERIOD_LABELS = {
    "today": "Today",
    "tomorrow": "Tomorrow",
    "this-week": "This week",
    "next-week": "Next week",
    "this-month": "This month",
    "next-month": "Next month",
    "this-year": "This year",
    "next-year": "Next year",
}

# Transit planets per period scale. The moon only means something for a day;
# fast inner planets drop out of the year view where Jupiter/Saturn dominate.
_DAY_PLANETS = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn")
_MID_PLANETS = ("sun", "mercury", "venus", "mars", "jupiter", "saturn")
_YEAR_PLANETS = ("jupiter", "saturn", "rahu", "ketu")


class HoroscopeGenerationError(Exception):
    """The LLM call failed or returned an unusable shape."""


@dataclass(frozen=True)
class PeriodSpec:
    token: str
    label: str
    period_type: str  # day | week | month | year
    period_key: str
    start: date
    end: date  # inclusive
    ref_date: date  # transit snapshot moment (midpoint-ish)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, 12, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def resolve_period(token: str, today: date | None = None) -> PeriodSpec:
    today = today or date.today()
    label = PERIOD_LABELS[token]

    if token in ("today", "tomorrow"):
        day = today if token == "today" else today + timedelta(days=1)
        return PeriodSpec(token, label, "day", day.isoformat(), day, day, day)

    if token in ("this-week", "next-week"):
        monday = today - timedelta(days=today.weekday())
        if token == "next-week":
            monday += timedelta(days=7)
        iso = monday.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        # Wednesday as the transit snapshot for the week.
        return PeriodSpec(
            token,
            label,
            "week",
            key,
            monday,
            monday + timedelta(days=6),
            monday + timedelta(days=2),
        )

    if token in ("this-month", "next-month"):
        year, month = today.year, today.month
        if token == "next-month":
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        start, end = _month_bounds(year, month)
        return PeriodSpec(
            token, label, "month", f"{year}-{month:02d}", start, end, date(year, month, 15)
        )

    if token in ("this-year", "next-year"):
        year = today.year + (1 if token == "next-year" else 0)
        return PeriodSpec(
            token, label, "year", str(year), date(year, 1, 1), date(year, 12, 31), date(year, 7, 1)
        )

    raise KeyError(token)


# ---------------------------------------------------------------------------
# Cache reads
# ---------------------------------------------------------------------------


def cached_readings(db: DbSession, spec: PeriodSpec) -> dict[str, HoroscopeReading]:
    statement = select(HoroscopeReading).where(
        HoroscopeReading.period_type == spec.period_type,
        HoroscopeReading.period_key == spec.period_key,
    )
    return {reading.system: reading for reading in db.scalars(statement)}


def cached_period_keys(db: DbSession) -> set[tuple[str, str]]:
    """(period_type, period_key) pairs with a full set of system readings."""
    statement = select(HoroscopeReading.period_type, HoroscopeReading.period_key)
    counts: dict[tuple[str, str], int] = {}
    for period_type, period_key in db.execute(statement):
        counts[(period_type, period_key)] = counts.get((period_type, period_key), 0) + 1
    return {key for key, count in counts.items() if count >= len(SYSTEMS)}


# ---------------------------------------------------------------------------
# Period facts → prompt
# ---------------------------------------------------------------------------


def _transit_block(
    spec: PeriodSpec, *, sidereal: bool, reference_sign: int, reference_name: str
) -> dict[str, dict]:
    longitudes = astro.body_longitudes(astro.utc_noon(spec.ref_date), sidereal=sidereal)
    if spec.period_type == "day":
        planets = _DAY_PLANETS
    elif spec.period_type == "year":
        planets = _YEAR_PLANETS
    else:
        planets = _MID_PLANETS
    block = {}
    for planet in planets:
        idx = astro.sign_index(longitudes[planet])
        block[planet] = {
            "sign": astro.sign_name(longitudes[planet], vedic=sidereal),
            reference_name: astro.whole_sign_house(reference_sign, idx),
        }
    return block


def _western_sign_index(natal: dict, key: str) -> int:
    return astro.SIGNS.index(natal["western"][key])


def _vedic_sign_index(natal: dict, key: str) -> int:
    # Vedic signs are stored as "Mithuna (Gemini)" — index by the Western name.
    western_name = natal["vedic"][key].split("(")[-1].rstrip(")")
    return astro.SIGNS.index(western_name)


def period_facts(natal: dict, spec: PeriodSpec) -> dict:
    """The grounded-facts payload the LLM writes from. No birth data."""
    facts: dict = {
        "period": {
            "label": spec.label,
            "type": spec.period_type,
            "range": f"{spec.start.isoformat()} to {spec.end.isoformat()}",
        },
        "western": {
            "natal": natal["western"],
            "transits": _transit_block(
                spec,
                sidereal=False,
                reference_sign=_western_sign_index(natal, "ascendant_sign"),
                reference_name="house_from_ascendant",
            ),
        },
        "vedic": {
            "natal": {k: v for k, v in natal["vedic"].items() if k != "dasha_timeline"},
            "transits": _transit_block(
                spec,
                sidereal=True,
                reference_sign=_vedic_sign_index(natal, "moon_sign"),
                reference_name="house_from_moon",
            ),
        },
        "chinese": {
            "natal": natal["chinese"],
            "period_year": astro.chinese_year_pillar(spec.ref_date),
        },
    }
    dasha = astro.active_dasha(natal["vedic"].get("dasha_timeline", []), spec.ref_date)
    if dasha is not None:
        facts["vedic"]["dasha"] = {"maha": dasha["maha"], "antar": dasha["antar"]}
    return facts


_SYSTEM_PROMPT = (
    "You write horoscope readings for a private family app, one shared profile. "
    "You receive precomputed astrological facts for a period in three traditions: "
    "Vedic (sidereal transits counted as houses from the natal moon sign — gochara — "
    "plus the running Vimshottari maha/antar dasha), Chinese (natal year pillar vs the "
    "period's year pillar), and Western (tropical transits counted as houses from the "
    "natal ascendant). Write one reading per tradition, warm and specific, in second "
    "person, weaving in the supplied facts by name (planets, signs, houses, dasha lords, "
    "animals and elements) in plain language a non-astrologer enjoys. Never invent "
    "positions beyond the facts given, never mention birth details, and give no medical, "
    "legal, or financial advice — this is reflective entertainment. "
    'Respond with one JSON object exactly: {"vedic": "...", "chinese": "...", '
    '"western": "..."} — each value a single plain-text reading of 90 to 140 words, '
    "no markdown, no headings."
)


def build_messages(natal: dict, spec: PeriodSpec) -> list[dict[str, str]]:
    payload = {"facts": period_facts(natal, spec)}
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# ---------------------------------------------------------------------------
# Generate and cache
# ---------------------------------------------------------------------------


def generate_readings(
    db: DbSession,
    *,
    llm: LLMClient,
    natal: dict,
    spec: PeriodSpec,
    model_label: str | None,
) -> dict[str, HoroscopeReading]:
    """Generate the period's missing readings via the LLM and persist them.

    Idempotent: systems already cached are kept as-is; a concurrent insert
    losing the unique-constraint race falls back to the surviving row.
    """
    existing = cached_readings(db, spec)
    missing = [system for system in SYSTEMS if system not in existing]
    if not missing:
        return existing

    try:
        response = llm.chat_json(build_messages(natal, spec))
    except Exception as exc:  # httpx errors, JSON decode — one user-facing failure
        raise HoroscopeGenerationError(
            "The stars are unreachable right now — the language model call failed. Try again."
        ) from exc

    for system in missing:
        content = response.get(system)
        if not isinstance(content, str) or not content.strip():
            raise HoroscopeGenerationError(
                "The language model returned an unusable reading. Try again."
            )
        reading = HoroscopeReading(
            system=system,
            period_type=spec.period_type,
            period_key=spec.period_key,
            content=content.strip(),
            model=model_label,
        )
        db.add(reading)
        existing[system] = reading
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return cached_readings(db, spec)
    return existing


class CannedHoroscopeLLM:
    """Offline stand-in (USE_MOCK_LLM=true): fixed text, no inference."""

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, str]:
        canned = (
            "A steady stretch: the mock stars counsel patience, tidy plans, "
            "and one small brave step. (Offline mode — no model was consulted.)"
        )
        return {system: canned for system in SYSTEMS}
