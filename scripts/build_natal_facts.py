"""Build the natal-facts file for the horoscope module — run LOCALLY, never on the server.

Takes the household profile's birth details and writes only derived chart
facts (signs, nakshatra, dasha timeline, year pillar) to a JSON file. The raw
birth date/time/place stay on the machine where you run this; deploy just the
output file into the server's gitignored ``Data/`` mount (PRD §21 Phase 4).

Usage:
    uv run python scripts/build_natal_facts.py \
        --date 1990-01-31 --time 12:16 --tz Asia/Kolkata \
        --lat 19.0760 --lon 72.8777

Verify the printed summary against a trusted birth-chart source before
deploying. Longitude is degrees east (negative = west).
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from family_assistant.horoscope import astro

WESTERN_PLANETS = ("sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn")
VEDIC_PLANETS = (*WESTERN_PLANETS, "rahu", "ketu")


def build_facts(birth_local: datetime, latitude: float, longitude: float) -> dict:
    birth_utc = birth_local.astimezone(UTC)
    birth_date = birth_local.date()

    tropical = astro.body_longitudes(birth_utc, sidereal=False)
    sidereal = astro.body_longitudes(birth_utc, sidereal=True)
    asc_tropical = astro.ascendant(birth_utc, latitude, longitude, sidereal=False)
    asc_sidereal = astro.ascendant(birth_utc, latitude, longitude, sidereal=True)
    nakshatra, pada, _ = astro.nakshatra_of(sidereal["moon"])

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "western": {
            "sun_sign": astro.sign_name(tropical["sun"]),
            "moon_sign": astro.sign_name(tropical["moon"]),
            "ascendant_sign": astro.sign_name(asc_tropical),
            "planet_signs": {p: astro.sign_name(tropical[p]) for p in WESTERN_PLANETS},
        },
        "vedic": {
            "moon_sign": astro.sign_name(sidereal["moon"], vedic=True),
            "nakshatra": nakshatra,
            "pada": pada,
            "ascendant_sign": astro.sign_name(asc_sidereal, vedic=True),
            "planet_signs": {p: astro.sign_name(sidereal[p], vedic=True) for p in VEDIC_PLANETS},
            "dasha_timeline": astro.vimshottari_timeline(sidereal["moon"], birth_date),
        },
        "chinese": astro.chinese_year_pillar(birth_date),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, help="Birth date, YYYY-MM-DD")
    parser.add_argument("--time", required=True, help="Local birth time, HH:MM (24h)")
    parser.add_argument("--tz", required=True, help="IANA timezone, e.g. Asia/Kolkata")
    parser.add_argument("--lat", required=True, type=float, help="Birthplace latitude")
    parser.add_argument("--lon", required=True, type=float, help="Birthplace longitude (east +)")
    parser.add_argument("--out", default="Data/natal_facts.json", help="Output path")
    args = parser.parse_args()

    birth_local = datetime.combine(
        date.fromisoformat(args.date),
        datetime.strptime(args.time, "%H:%M").time(),
        tzinfo=ZoneInfo(args.tz),
    )
    facts = build_facts(birth_local, args.lat, args.lon)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n")

    western, vedic, chinese = facts["western"], facts["vedic"], facts["chinese"]
    current = astro.active_dasha(vedic["dasha_timeline"], date.today()) or {}
    print(f"Wrote {out} (no birth data inside — derived facts only)\n")
    print(
        f"Western : Sun {western['sun_sign']} · Moon {western['moon_sign']} · "
        f"Asc {western['ascendant_sign']}"
    )
    print(
        f"Vedic   : Moon {vedic['moon_sign']} · {vedic['nakshatra']} pada {vedic['pada']} · "
        f"Lagna {vedic['ascendant_sign']}"
    )
    print(f"          Current dasha {current.get('maha', '?')}/{current.get('antar', '?')}")
    print(f"Chinese : {chinese['polarity']} {chinese['element']} {chinese['animal']}")
    print(
        "\nCheck these against a trusted chart source, then deploy the file "
        "to the server's Data/ directory."
    )


if __name__ == "__main__":
    main()
