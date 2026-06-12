"""Horoscope module tests: astro math, period resolution, lazy generate-and-
cache service, and the routes (with the LLM faked and natal facts stubbed)."""

import itertools
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from family_assistant.horoscope import astro
from family_assistant.horoscope.router import get_horoscope_llm
from family_assistant.horoscope.services import (
    SYSTEMS,
    cached_readings,
    generate_readings,
    period_facts,
    resolve_period,
)
from family_assistant.main import app

# Derived facts only — the same shape scripts/build_natal_facts.py emits.
NATAL = {
    "western": {
        "sun_sign": "Gemini",
        "moon_sign": "Cancer",
        "ascendant_sign": "Virgo",
        "planet_signs": {"sun": "Gemini", "moon": "Cancer"},
    },
    "vedic": {
        "moon_sign": "Mithuna (Gemini)",
        "nakshatra": "Punarvasu",
        "pada": 2,
        "ascendant_sign": "Simha (Leo)",
        "planet_signs": {"moon": "Mithuna (Gemini)"},
        "dasha_timeline": [
            {"maha": "Mercury", "antar": "Sun", "start": "2025-01-01", "end": "2027-01-01"},
        ],
    },
    "chinese": {"animal": "Snake", "element": "Earth", "polarity": "Yin"},
}


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat_json(self, messages):
        self.calls += 1
        return {system: f"A fine {system} spell ahead." for system in SYSTEMS}


# ---------------------------------------------------------------------------
# Pure astro helpers
# ---------------------------------------------------------------------------


def test_sign_name_boundaries() -> None:
    assert astro.sign_name(0.0) == "Aries"
    assert astro.sign_name(75.5) == "Gemini"
    assert astro.sign_name(359.9) == "Pisces"
    assert astro.sign_name(75.5, vedic=True) == "Mithuna (Gemini)"


def test_nakshatra_of() -> None:
    # Sidereal moon ~83.74° → Punarvasu (7th nakshatra), pada 2.
    name, pada, fraction = astro.nakshatra_of(83.74)
    assert name == "Punarvasu"
    assert pada == 2
    assert 0.25 <= fraction < 0.5


def test_whole_sign_house() -> None:
    assert astro.whole_sign_house(5, 5) == 1
    assert astro.whole_sign_house(0, 11) == 12
    assert astro.whole_sign_house(11, 0) == 2


def test_chinese_year_pillar_respects_lunar_new_year() -> None:
    # Mid-1989 is the Yin Earth Snake year...
    assert astro.chinese_year_pillar(date(1989, 6, 6)) == {
        "animal": "Snake",
        "element": "Earth",
        "polarity": "Yin",
    }
    # ...but mid-January 1989 is still the 1988 Yang Earth Dragon year.
    assert astro.chinese_year_pillar(date(1989, 1, 15)) == {
        "animal": "Dragon",
        "element": "Earth",
        "polarity": "Yang",
    }


def test_vimshottari_timeline_contiguous_and_120_years() -> None:
    birth = date(1989, 6, 6)
    timeline = astro.vimshottari_timeline(83.74, birth)
    assert timeline[0]["start"] == birth.isoformat()
    for prev, nxt in itertools.pairwise(timeline):
        assert prev["end"] == nxt["start"]
    lords = {entry["maha"] for entry in timeline}
    assert lords == {lord for lord, _ in astro.DASHA_SEQUENCE}
    # Punarvasu's lord is Jupiter; the natal balance dasha comes first.
    assert timeline[0]["maha"] == "Jupiter"
    span_days = date.fromisoformat(timeline[-1]["end"]) - birth
    assert 100 * 365 < span_days.days < 120 * 366  # 120y minus the pre-birth balance


def test_active_dasha_lookup() -> None:
    timeline = astro.vimshottari_timeline(83.74, date(1989, 6, 6))
    current = astro.active_dasha(timeline, date(2026, 6, 12))
    assert current is not None
    assert current["maha"] == "Mercury"
    assert astro.active_dasha(timeline, date(1900, 1, 1)) is None


# ---------------------------------------------------------------------------
# Period resolution
# ---------------------------------------------------------------------------


def test_resolve_period_keys() -> None:
    today = date(2026, 6, 12)  # a Friday in ISO week 24
    assert resolve_period("today", today).period_key == "2026-06-12"
    assert resolve_period("tomorrow", today).period_key == "2026-06-13"

    week = resolve_period("this-week", today)
    assert (week.period_key, week.start, week.end) == (
        "2026-W24",
        date(2026, 6, 8),
        date(2026, 6, 14),
    )
    assert week.ref_date == date(2026, 6, 10)  # Wednesday snapshot
    assert resolve_period("next-week", today).period_key == "2026-W25"

    month = resolve_period("this-month", today)
    assert (month.period_key, month.end) == ("2026-06", date(2026, 6, 30))
    assert resolve_period("next-month", today).period_key == "2026-07"
    assert resolve_period("this-year", today).period_key == "2026"
    assert resolve_period("next-year", today).period_key == "2027"


def test_resolve_period_december_rollover() -> None:
    today = date(2026, 12, 20)
    assert resolve_period("next-month", today).period_key == "2027-01"
    assert resolve_period("next-year", today).period_key == "2027"


# ---------------------------------------------------------------------------
# Facts payload
# ---------------------------------------------------------------------------


def test_period_facts_grounded_and_clean() -> None:
    spec = resolve_period("this-week", date(2026, 6, 12))
    facts = period_facts(NATAL, spec)
    assert facts["vedic"]["dasha"] == {"maha": "Mercury", "antar": "Sun"}
    # The 81-entry timeline stays out of the prompt payload.
    assert "dasha_timeline" not in facts["vedic"]["natal"]
    for planet, transit in facts["western"]["transits"].items():
        assert transit["sign"] in [str(s) for s in astro.SIGNS]
        assert 1 <= transit["house_from_ascendant"] <= 12
        assert planet != "moon"  # moon only appears in day-scale facts
    day_facts = period_facts(NATAL, resolve_period("today", date(2026, 6, 12)))
    assert "moon" in day_facts["western"]["transits"]
    year_facts = period_facts(NATAL, resolve_period("this-year", date(2026, 6, 12)))
    assert set(year_facts["vedic"]["transits"]) == {"jupiter", "saturn", "rahu", "ketu"}
    assert facts["chinese"]["period_year"]["animal"] == "Horse"  # 2026


# ---------------------------------------------------------------------------
# Generate-and-cache service
# ---------------------------------------------------------------------------


def test_generate_readings_caches_per_period(db_session: Session) -> None:
    spec = resolve_period("today", date(2026, 6, 12))
    llm = FakeLLM()
    readings = generate_readings(
        db_session, llm=llm, natal=NATAL, spec=spec, model_label="test-model"
    )
    assert set(readings) == set(SYSTEMS)
    assert llm.calls == 1

    # Second call is a pure cache hit — no LLM call, same rows.
    again = generate_readings(db_session, llm=llm, natal=NATAL, spec=spec, model_label="test-model")
    assert llm.calls == 1
    assert {r.id for r in again.values()} == {r.id for r in readings.values()}
    assert set(cached_readings(db_session, spec)) == set(SYSTEMS)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _stub_natal(monkeypatch, value) -> None:
    monkeypatch.setattr("family_assistant.horoscope.router.load_natal_facts", lambda: value)


def test_index_lists_periods(authenticated_client: TestClient, monkeypatch) -> None:
    _stub_natal(monkeypatch, NATAL)
    response = authenticated_client.get("/horoscope")
    assert response.status_code == 200
    for label in ("Today", "Tomorrow", "This week", "Next year"):
        assert label in response.text
    assert "Tap to reveal" in response.text


def test_index_without_natal_shows_setup_hint(
    authenticated_client: TestClient, monkeypatch
) -> None:
    _stub_natal(monkeypatch, None)
    response = authenticated_client.get("/horoscope")
    assert response.status_code == 200
    assert "Natal facts file not found" in response.text
    # Period pages bounce back to the landing page.
    bounced = authenticated_client.get("/horoscope/today", follow_redirects=False)
    assert bounced.status_code == 303


def test_unknown_period_redirects(authenticated_client: TestClient, monkeypatch) -> None:
    _stub_natal(monkeypatch, NATAL)
    response = authenticated_client.get("/horoscope/yesteryear", follow_redirects=False)
    assert response.status_code == 303


def test_reveal_generates_then_serves_cached(authenticated_client: TestClient, monkeypatch) -> None:
    _stub_natal(monkeypatch, NATAL)
    llm = FakeLLM()
    app.dependency_overrides[get_horoscope_llm] = lambda: llm

    before = authenticated_client.get("/horoscope/today")
    assert "Reveal today" in before.text

    response = authenticated_client.post("/horoscope/today/reveal", follow_redirects=False)
    assert response.status_code == 303
    assert llm.calls == 1

    after = authenticated_client.get("/horoscope/today")
    assert "A fine vedic spell ahead." in after.text
    assert "A fine western spell ahead." in after.text
    assert "Reveal today" not in after.text
