"""Fixed exercise-catalog vocabulary (PRD §10.16 step 1).

Muscles are a closed list so weekly coverage can tell push from pull and front
from back; free-text tags made that impossible. Each exercise names primary
muscles (credited in full) and secondary muscles (credited at half).
"""

from decimal import Decimal

REGIONS: tuple[str, ...] = ("upper", "lower", "core", "full")
MODALITIES: tuple[str, ...] = ("strength", "cardio")
LOCATIONS: tuple[str, ...] = ("gym", "home", "both")

# Display groups, in order. Every muscle belongs to exactly one group.
MUSCLE_GROUPS: dict[str, tuple[str, ...]] = {
    "Upper push": ("chest", "front_delts", "side_delts", "triceps"),
    "Upper pull": ("upper_back", "rear_delts", "biceps", "forearms"),
    "Core": ("abs", "lower_back", "hip_flexors"),
    "Lower": ("quads", "hamstrings", "glutes", "adductors", "calves"),
}
MUSCLES: tuple[str, ...] = tuple(m for group in MUSCLE_GROUPS.values() for m in group)

PRIMARY_CREDIT = Decimal("1")
SECONDARY_CREDIT = Decimal("0.5")


def muscle_label(muscle: str) -> str:
    """``front_delts`` -> ``Front delts``."""
    return muscle.replace("_", " ").capitalize()
