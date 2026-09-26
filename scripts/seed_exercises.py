"""Seed the household exercise catalog (PRD §10.16 re-tag).

One-off, idempotent import: creates each exercise in the shared ``exercises``
table via the normal service layer (so vocabulary validation applies).
Existing exercises (matched case-insensitively by name) are skipped, so
re-running is safe. For a fresh install; an existing catalog is re-tagged by
migration ``0026`` instead.

This seeds only the *catalog* — no per-user log history is imported.

Run inside the app container:

    docker compose exec -T app python scripts/seed_exercises.py
"""

from __future__ import annotations

from decimal import Decimal

from family_assistant.db import get_sessionmaker
from family_assistant.exercise.services import create_exercise, get_exercise_by_name

# (name, region, modality, location, primary, secondary, scoring_type, bodyweight_fraction)
# Same table as migration 0026. Cardio "primary" muscles are the ones it keeps from
# going stale; cardio is scored in minutes.
CATALOG: list[tuple[str, str, str, str, list[str], list[str], str, Decimal]] = [
    (
        "Chest press machine",
        "upper",
        "strength",
        "gym",
        ["chest"],
        ["triceps", "front_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Pec fly machine",
        "upper",
        "strength",
        "gym",
        ["chest"],
        ["front_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Dumbbell bench press",
        "upper",
        "strength",
        "both",
        ["chest"],
        ["triceps", "front_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Pushups",
        "upper",
        "strength",
        "home",
        ["chest"],
        ["triceps", "front_delts", "abs"],
        "bodyweight_fraction",
        Decimal("0.640"),
    ),
    (
        "Dumbbell shoulder press",
        "upper",
        "strength",
        "both",
        ["front_delts"],
        ["side_delts", "triceps"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Shoulder press machine",
        "upper",
        "strength",
        "gym",
        ["front_delts"],
        ["side_delts", "triceps"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Front raise", "upper", "strength", "both", ["front_delts"], [], "weighted", Decimal("1.000")),
    (
        "Lateral Raise",
        "upper",
        "strength",
        "both",
        ["side_delts"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    ("Triceps pushdown", "upper", "strength", "gym", ["triceps"], [], "weighted", Decimal("1.000")),
    (
        "Triceps extension machine",
        "upper",
        "strength",
        "gym",
        ["triceps"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Triceps kickback",
        "upper",
        "strength",
        "both",
        ["triceps"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Overhead Dumbbell Triceps Extension",
        "upper",
        "strength",
        "both",
        ["triceps"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Lat pulldown",
        "upper",
        "strength",
        "gym",
        ["upper_back"],
        ["biceps", "rear_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Seated Cable Row",
        "upper",
        "strength",
        "gym",
        ["upper_back"],
        ["biceps", "rear_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Single Arm Row",
        "upper",
        "strength",
        "both",
        ["upper_back"],
        ["biceps", "rear_delts"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Rear Delt Pec Fly Machine",
        "upper",
        "strength",
        "gym",
        ["rear_delts"],
        ["upper_back"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Hammer Curl",
        "upper",
        "strength",
        "both",
        ["biceps"],
        ["forearms"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Barbell curl",
        "upper",
        "strength",
        "gym",
        ["biceps"],
        ["forearms"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Seated dumbbell curl",
        "upper",
        "strength",
        "both",
        ["biceps"],
        ["forearms"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Concentration curl",
        "upper",
        "strength",
        "both",
        ["biceps"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Arm curl machine",
        "upper",
        "strength",
        "gym",
        ["biceps"],
        ["forearms"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Sit-ups",
        "core",
        "strength",
        "home",
        ["abs"],
        ["hip_flexors"],
        "bodyweight_fraction",
        Decimal("0.380"),
    ),
    (
        "Abdominal machine",
        "core",
        "strength",
        "gym",
        ["abs"],
        ["hip_flexors"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Captain's Chair Leg Raise",
        "core",
        "strength",
        "gym",
        ["abs", "hip_flexors"],
        [],
        "bodyweight_fraction",
        Decimal("0.500"),
    ),
    (
        "Leg raise",
        "core",
        "strength",
        "gym",
        ["abs", "hip_flexors"],
        [],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Leg Raise unweighted",
        "core",
        "strength",
        "both",
        ["abs", "hip_flexors"],
        [],
        "bodyweight_fraction",
        Decimal("0.400"),
    ),
    (
        "Back Extension Machine",
        "core",
        "strength",
        "gym",
        ["lower_back"],
        ["glutes", "hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Hack squat",
        "lower",
        "strength",
        "gym",
        ["quads"],
        ["glutes", "adductors"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Leg press",
        "lower",
        "strength",
        "gym",
        ["quads", "glutes"],
        ["hamstrings", "adductors"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Leg extension", "lower", "strength", "gym", ["quads"], [], "weighted", Decimal("1.000")),
    (
        "Leg curl",
        "lower",
        "strength",
        "gym",
        ["hamstrings"],
        ["calves"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Dumbbell squat",
        "lower",
        "strength",
        "both",
        ["quads", "glutes"],
        ["adductors"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Romanian Dead Lift",
        "lower",
        "strength",
        "both",
        ["hamstrings", "glutes"],
        ["lower_back", "forearms"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Kettle Bell Swing",
        "lower",
        "strength",
        "both",
        ["glutes", "hamstrings"],
        ["lower_back", "abs"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Hiking",
        "full",
        "cardio",
        "both",
        ["quads", "glutes", "calves"],
        [],
        "timed",
        Decimal("1.000"),
    ),
    ("Treadmill", "lower", "cardio", "gym", ["calves"], [], "timed", Decimal("1.000")),
    (
        "StairMaster",
        "lower",
        "cardio",
        "gym",
        ["quads", "glutes", "calves"],
        [],
        "timed",
        Decimal("1.000"),
    ),
    (
        "Rowing machine",
        "full",
        "cardio",
        "home",
        ["upper_back", "quads"],
        [],
        "timed",
        Decimal("1.000"),
    ),
]


def main() -> None:
    created = 0
    skipped = 0
    with get_sessionmaker()() as db:
        for name, region, modality, location, primary, secondary, scoring, fraction in CATALOG:
            if get_exercise_by_name(db, name) is not None:
                print(f"skip   {name} (already exists)")
                skipped += 1
                continue
            create_exercise(
                db,
                name=name,
                region=region,
                modality=modality,
                location=location,
                primary_muscles=primary,
                secondary_muscles=secondary,
                scoring_type=scoring,
                bodyweight_fraction=fraction,
            )
            print(f"create {name}")
            created += 1
    print(f"\nDone: {created} created, {skipped} skipped, {len(CATALOG)} total.")


if __name__ == "__main__":
    main()
