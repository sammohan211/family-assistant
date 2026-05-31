"""Seed the household exercise catalog from the 2024 Notion export.

One-off, idempotent import: creates each unique exercise from
``Data/Exercise_Log_2024.csv`` in the shared ``exercises`` table via the
normal service layer (so validation + tag normalization apply). Existing
exercises (matched case-insensitively by name) are skipped, so re-running is
safe.

This seeds only the *catalog* — no per-user log history is imported.

Run inside the app container:

    docker compose exec -T app python scripts/seed_exercises.py
"""

from __future__ import annotations

from decimal import Decimal

from family_assistant.db import get_sessionmaker
from family_assistant.exercise.services import create_exercise, get_exercise_by_name

# (name, body_group, muscle_groups, scoring_type, bodyweight_fraction)
# Derived from Data/Exercise_Log_2024.csv — body_group and muscle_groups taken
# verbatim from the log; scoring_type inferred from how each was logged.
CATALOG: list[tuple[str, str, list[str], str, Decimal]] = [
    ("Abdominal machine", "core", ["Abdominals and Lower Back"], "weighted", Decimal("1.000")),
    ("Arm curl machine", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
    ("Back Extension Machine", "core", ["Erector Spinae"], "weighted", Decimal("1.000")),
    ("Barbell curl", "upper", ["Biceps and Triceps", "Forearms"], "weighted", Decimal("1.000")),
    (
        "Captain's Chair Leg Raise",
        "lower",
        ["Abdominals and Lower Back", "Core", "Hip Flexors and Outer Hips"],
        "bodyweight_fraction",
        Decimal("1.000"),
    ),
    (
        "Chest press machine",
        "upper",
        ["Biceps and Triceps", "Chest Upper and Middle Back", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Concentration curl", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
    (
        "Dumbbell bench press",
        "upper",
        ["Biceps and Triceps", "Chest Upper and Middle Back", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Dumbbell shoulder press",
        "upper",
        ["Biceps and Triceps", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Dumbbell squat",
        "lower",
        ["Buttocks", "Hip Flexors and Outer Hips", "Inner Thighs", "Quadriceps and Hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Flat Dumbbell Press", "upper", ["Chest Upper and Middle Back"], "weighted", Decimal("1.000")),
    ("Front raise", "upper", ["Front Delts", "Shoulders"], "weighted", Decimal("1.000")),
    (
        "Hack squat",
        "lower",
        ["Buttocks", "Hip Flexors and Outer Hips", "Quadriceps and Hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Hammer Curl", "upper", ["Biceps and Triceps", "Forearms"], "weighted", Decimal("1.000")),
    ("Hiking", "cardio", ["Heart and Lungs"], "distance", Decimal("1.000")),
    (
        "Kettle Bell Swing",
        "core",
        ["Core", "Glutes", "Hamstring"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Lat pulldown",
        "upper",
        ["Biceps and Triceps", "Chest Upper and Middle Back", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Lateral Raise", "upper", ["Lateral Delts", "Shoulders"], "weighted", Decimal("1.000")),
    (
        "Leg curl",
        "lower",
        ["Buttocks", "Calves and Shins", "Quadriceps and Hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Leg extension",
        "lower",
        ["Buttocks", "Calves and Shins", "Quadriceps and Hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Leg press",
        "lower",
        ["Inner Thighs", "Quadriceps and Hamstrings"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Leg raise",
        "core",
        ["Abdominals and Lower Back", "Hip Flexors and Outer Hips"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Pec fly machine",
        "upper",
        ["Biceps and Triceps", "Chest Upper and Middle Back", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Rear Delt Pec Fly Machine",
        "upper",
        ["Rear Delts", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Romanian Dead Lift",
        "lower",
        ["Biceps and Triceps", "Glutes", "Quadriceps and Hamstrings", "Upper Back"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Row Machine", "upper", ["Upper Back"], "weighted", Decimal("1.000")),
    (
        "Seated Cable Row",
        "upper",
        ["Biceps and Triceps", "Core", "Upper Back"],
        "weighted",
        Decimal("1.000"),
    ),
    ("Seated dumbbell curl", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
    (
        "Shoulder press machine",
        "upper",
        ["Biceps and Triceps", "Shoulders"],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "Single Arm Row",
        "upper",
        [
            "Biceps and Triceps",
            "Core",
            "Front Delts",
            "Lateral Delts",
            "Rear Delts",
            "Upper Back",
        ],
        "weighted",
        Decimal("1.000"),
    ),
    (
        "StairMaster",
        "lower",
        ["Calves and Shins", "Core", "Hip Flexors and Outer Hips", "Quadriceps and Hamstrings"],
        "distance",
        Decimal("1.000"),
    ),
    ("Treadmill", "cardio", ["Heart and Lungs"], "distance", Decimal("1.000")),
    ("Triceps extension machine", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
    ("Triceps kickback", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
    ("Triceps pushdown", "upper", ["Biceps and Triceps"], "weighted", Decimal("1.000")),
]


def main() -> None:
    created = 0
    skipped = 0
    with get_sessionmaker()() as db:
        for name, body_group, muscle_groups, scoring_type, fraction in CATALOG:
            if get_exercise_by_name(db, name) is not None:
                print(f"skip   {name} (already exists)")
                skipped += 1
                continue
            create_exercise(
                db,
                name=name,
                body_group=body_group,
                muscle_groups=muscle_groups,
                scoring_type=scoring_type,
                bodyweight_fraction=fraction,
            )
            print(f"create {name}")
            created += 1
    print(f"\nDone: {created} created, {skipped} skipped, {len(CATALOG)} total.")


if __name__ == "__main__":
    main()
