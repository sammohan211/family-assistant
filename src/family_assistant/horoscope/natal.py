"""Load the precomputed natal-facts file.

The file is produced *off the server* by ``scripts/build_natal_facts.py`` from
the household's birth details and deployed as a read-only mount (gitignored
``Data/``). It contains only derived chart facts — signs, nakshatra, dasha
timeline, year pillar — never the raw birth date/time/place (PRD §21 Phase 4:
birth data never enters the cloud).
"""

import json
from pathlib import Path

from family_assistant.settings import get_settings

REQUIRED_SECTIONS = ("western", "vedic", "chinese")

_cache: dict[str, dict] = {}


def load_natal_facts() -> dict | None:
    """Parsed natal facts, or None when the file is missing/invalid.

    Cached per path after the first successful load; the file is immutable in
    practice (regenerating it means redeploying the mount).
    """
    path = Path(get_settings().natal_facts_path)
    key = str(path)
    if key in _cache:
        return _cache[key]
    try:
        facts = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not all(isinstance(facts.get(section), dict) for section in REQUIRED_SECTIONS):
        return None
    _cache[key] = facts
    return facts
