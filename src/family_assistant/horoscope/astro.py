"""Pure astrology math shared by the natal-facts builder script and the app.

Everything here is deterministic computation — Skyfield (JPL DE421 ephemeris,
bundled by ``skyfield-data``, valid 1899 to 2053) for planetary longitudes, plus
small classical formulas for the ascendant, the Lahiri ayanamsa, Vimshottari
dashas, and the Chinese sexagenary year cycle. The LLM never computes any of
this; it only writes prose around facts produced here (PRD §21 Phase 4).

Positions were verified against a reference natal chart (astro-charts.com,
tropical/Placidus): all seven bodies and the ascendant agree to ~1 arcminute.
The Lahiri ayanamsa uses a linear approximation around J2000 (about one
arcminute across recent decades) — fine for sign/nakshatra labels in an
entertainment feature.
"""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from math import atan2, cos, degrees, radians, sin, tan

from lunardate import LunarDate
from skyfield.api import Loader
from skyfield_data import get_skyfield_data_path

SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

# Sanskrit names shown alongside the Western ones in Vedic facts.
VEDIC_SIGNS = (
    "Mesha",
    "Vrishabha",
    "Mithuna",
    "Karka",
    "Simha",
    "Kanya",
    "Tula",
    "Vrishchika",
    "Dhanu",
    "Makara",
    "Kumbha",
    "Meena",
)

NAKSHATRAS = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
)

# Vimshottari maha-dasha sequence: (lord, years), 120 years total. The cycle
# starts from the lord of the natal moon's nakshatra (nakshatra index mod 9).
DASHA_SEQUENCE = (
    ("Ketu", 7),
    ("Venus", 20),
    ("Sun", 6),
    ("Moon", 10),
    ("Mars", 7),
    ("Rahu", 18),
    ("Jupiter", 16),
    ("Saturn", 19),
    ("Mercury", 17),
)

CHINESE_ANIMALS = (
    "Rat",
    "Ox",
    "Tiger",
    "Rabbit",
    "Dragon",
    "Snake",
    "Horse",
    "Goat",
    "Monkey",
    "Rooster",
    "Dog",
    "Pig",
)

# Heavenly-stem elements repeat in yang/yin pairs: Wood Wood Fire Fire ...
STEM_ELEMENTS = (
    "Wood",
    "Wood",
    "Fire",
    "Fire",
    "Earth",
    "Earth",
    "Metal",
    "Metal",
    "Water",
    "Water",
)

# Skyfield body keys in DE421. Jupiter/Saturn barycenters are within
# arcminutes of the planets themselves for geocentric longitude.
BODIES = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
}

NAKSHATRA_SPAN = 360.0 / 27.0
SIGN_SPAN = 30.0
DASHA_YEAR_DAYS = 365.25


@lru_cache(maxsize=1)
def _sky():
    load = Loader(get_skyfield_data_path(), verbose=False)
    return load.timescale(), load("de421.bsp")


def _julian_centuries_tt(t) -> float:
    return (t.tt - 2451545.0) / 36525.0


def lahiri_ayanamsa(dt_utc: datetime) -> float:
    """Lahiri (Chitrapaksha) ayanamsa, linear approximation around J2000."""
    ts, _ = _sky()
    t = ts.from_datetime(dt_utc)
    years_since_2000 = (t.tt - 2451545.0) / 365.25
    return 23.853 + 0.0139688 * years_since_2000


def body_longitudes(dt_utc: datetime, *, sidereal: bool = False) -> dict[str, float]:
    """Geocentric apparent ecliptic-of-date longitudes, degrees [0, 360).

    Includes the seven classical bodies plus the mean lunar nodes Rahu/Ketu
    (used by the Vedic chart; harmless extras for the Western one).
    """
    ts, eph = _sky()
    t = ts.from_datetime(dt_utc)
    earth = eph["earth"]
    longitudes: dict[str, float] = {}
    for name, key in BODIES.items():
        _, lon, _ = earth.at(t).observe(eph[key]).apparent().ecliptic_latlon(epoch="date")
        longitudes[name] = lon.degrees % 360.0
    # Mean lunar node (Meeus): omega = 125.04452 - 1934.136261 * T degrees.
    t_c = _julian_centuries_tt(t)
    rahu = (125.04452 - 1934.136261 * t_c) % 360.0
    longitudes["rahu"] = rahu
    longitudes["ketu"] = (rahu + 180.0) % 360.0
    if sidereal:
        ayanamsa = lahiri_ayanamsa(dt_utc)
        longitudes = {k: (v - ayanamsa) % 360.0 for k, v in longitudes.items()}
    return longitudes


def ascendant(
    dt_utc: datetime, latitude: float, longitude: float, *, sidereal: bool = False
) -> float:
    """Ecliptic longitude of the ascendant, degrees [0, 360).

    Classical formula from the local sidereal time (RAMC) and the obliquity
    of date; verified against a Placidus reference chart to ~1 arcminute.
    """
    ts, _ = _sky()
    t = ts.from_datetime(dt_utc)
    ramc = radians((t.gast * 15.0 + longitude) % 360.0)
    eps = radians(23.43929111 - 0.013004167 * _julian_centuries_tt(t))
    lat = radians(latitude)
    asc = degrees(atan2(cos(ramc), -(sin(ramc) * cos(eps) + tan(lat) * sin(eps)))) % 360.0
    if sidereal:
        asc = (asc - lahiri_ayanamsa(dt_utc)) % 360.0
    return asc


def sign_index(lon: float) -> int:
    return int(lon % 360.0 // SIGN_SPAN)


def sign_name(lon: float, *, vedic: bool = False) -> str:
    idx = sign_index(lon)
    if vedic:
        return f"{VEDIC_SIGNS[idx]} ({SIGNS[idx]})"
    return SIGNS[idx]


def nakshatra_of(sidereal_lon: float) -> tuple[str, int, float]:
    """Return (nakshatra name, pada 1-4, fraction elapsed within nakshatra)."""
    position = sidereal_lon % 360.0
    index = int(position // NAKSHATRA_SPAN)
    fraction = (position % NAKSHATRA_SPAN) / NAKSHATRA_SPAN
    pada = int(fraction * 4) + 1
    return NAKSHATRAS[index], pada, fraction


def whole_sign_house(from_sign: int, to_sign: int) -> int:
    """House (1-12) of ``to_sign`` counted from ``from_sign``, whole-sign style."""
    return (to_sign - from_sign) % 12 + 1


def vimshottari_timeline(moon_sidereal_lon: float, birth_date: date) -> list[dict[str, str]]:
    """Full 120-year Vimshottari maha/antar-dasha timeline from birth.

    Each entry: {"maha", "antar", "start", "end"} with ISO dates. The first
    maha-dasha is the natal nakshatra's lord with its balance prorated by how
    far the moon had progressed through the nakshatra at birth.
    """
    _, _, fraction = nakshatra_of(moon_sidereal_lon)
    nak_index = int(moon_sidereal_lon % 360.0 // NAKSHATRA_SPAN)
    first = nak_index % 9
    # Years of the first (natal) maha-dasha already elapsed at birth. Every
    # boundary is converted from cumulative years exactly once, from the same
    # birth anchor — adjacent entries share boundaries, so date truncation
    # (date + timedelta drops fractional days) can't open gaps between them.
    elapsed_years = fraction * DASHA_SEQUENCE[first][1]

    def boundary(cycle_years: float) -> date:
        return birth_date + timedelta(days=(cycle_years - elapsed_years) * DASHA_YEAR_DAYS)

    timeline: list[dict[str, str]] = []
    cursor = 0.0
    for step in range(9):
        lord, years = DASHA_SEQUENCE[(first + step) % 9]
        for sub_step in range(9):
            sub_lord, sub_years = DASHA_SEQUENCE[(first + step + sub_step) % 9]
            start_day = boundary(cursor)
            cursor += years * sub_years / 120.0
            end_day = boundary(cursor)
            if end_day > birth_date:  # skip pre-birth slices of the first maha
                timeline.append(
                    {
                        "maha": lord,
                        "antar": sub_lord,
                        "start": max(start_day, birth_date).isoformat(),
                        "end": end_day.isoformat(),
                    }
                )
    return timeline


def active_dasha(timeline: list[dict[str, str]], on: date) -> dict[str, str] | None:
    """The maha/antar dasha entry covering ``on``, or None outside the timeline."""
    key = on.isoformat()
    for entry in timeline:
        if entry["start"] <= key < entry["end"]:
            return entry
    return None


def chinese_year_pillar(on: date) -> dict[str, str]:
    """Sexagenary year pillar (animal, element, polarity) for a solar date.

    Uses the lunar calendar so dates before Chinese New Year belong to the
    previous year's pillar.
    """
    lunar_year = LunarDate.fromSolarDate(on.year, on.month, on.day).year
    branch = (lunar_year - 4) % 12
    stem = (lunar_year - 4) % 10
    return {
        "animal": CHINESE_ANIMALS[branch],
        "element": STEM_ELEMENTS[stem],
        "polarity": "Yang" if stem % 2 == 0 else "Yin",
    }


def utc_noon(on: date) -> datetime:
    """Noon UTC of a date — the transit snapshot moment for period facts."""
    return datetime(on.year, on.month, on.day, 12, tzinfo=UTC)
