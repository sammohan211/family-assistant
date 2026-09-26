"""exercise: fixed muscle vocabulary, region/modality/location, timed scoring

PRD §10.16 step 1. Replaces the free-text ``muscle_groups`` tags and the
``body_group`` column (which mixed body regions with "cardio") with:

- ``region`` (upper|lower|core|full), ``modality`` (strength|cardio),
  ``location`` (gym|home|both)
- ``primary_muscles`` / ``secondary_muscles`` from a fixed 16-muscle list
- a ``timed`` scoring type (score = duration minutes) for cardio
- ``exercise_logs.body_weight_used`` so an edit re-scores with the weight the
  log was first scored with

Re-tags the household's existing catalog by name (the reviewed table in PRD
§10.16). Exercises not in that table get defaults derived from their old
``body_group`` and no muscles; the catalog UI flags them for a pick. Log rows
keep their inputs; only the cardio exercises' logs are re-scored (to minutes).

Revision ID: 0026_exercise_catalog_remodel
Revises: 0025_glucose_readings
Create Date: 2026-09-26
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0026_exercise_catalog_remodel"
down_revision: str | None = "0025_glucose_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, region, modality, location, primary, secondary, new scoring_type or None)
# Frozen copy of the PRD §10.16 re-tag table; matched case-insensitively by name.
RETAG: list[tuple[str, str, str, str, list[str], list[str], str | None]] = [
    (
        "Chest press machine",
        "upper",
        "strength",
        "gym",
        ["chest"],
        ["triceps", "front_delts"],
        None,
    ),
    ("Pec fly machine", "upper", "strength", "gym", ["chest"], ["front_delts"], None),
    (
        "Dumbbell bench press",
        "upper",
        "strength",
        "both",
        ["chest"],
        ["triceps", "front_delts"],
        None,
    ),
    ("Pushups", "upper", "strength", "home", ["chest"], ["triceps", "front_delts", "abs"], None),
    (
        "Dumbbell shoulder press",
        "upper",
        "strength",
        "both",
        ["front_delts"],
        ["side_delts", "triceps"],
        None,
    ),
    (
        "Shoulder press machine",
        "upper",
        "strength",
        "gym",
        ["front_delts"],
        ["side_delts", "triceps"],
        None,
    ),
    ("Front raise", "upper", "strength", "both", ["front_delts"], [], None),
    ("Lateral Raise", "upper", "strength", "both", ["side_delts"], [], None),
    ("Triceps pushdown", "upper", "strength", "gym", ["triceps"], [], None),
    ("Triceps extension machine", "upper", "strength", "gym", ["triceps"], [], None),
    ("Triceps kickback", "upper", "strength", "both", ["triceps"], [], None),
    ("Overhead Dumbbell Triceps Extension", "upper", "strength", "both", ["triceps"], [], None),
    ("Lat pulldown", "upper", "strength", "gym", ["upper_back"], ["biceps", "rear_delts"], None),
    (
        "Seated Cable Row",
        "upper",
        "strength",
        "gym",
        ["upper_back"],
        ["biceps", "rear_delts"],
        None,
    ),
    ("Single Arm Row", "upper", "strength", "both", ["upper_back"], ["biceps", "rear_delts"], None),
    ("Rear Delt Pec Fly Machine", "upper", "strength", "gym", ["rear_delts"], ["upper_back"], None),
    ("Hammer Curl", "upper", "strength", "both", ["biceps"], ["forearms"], None),
    ("Barbell curl", "upper", "strength", "gym", ["biceps"], ["forearms"], None),
    ("Seated dumbbell curl", "upper", "strength", "both", ["biceps"], ["forearms"], None),
    ("Concentration curl", "upper", "strength", "both", ["biceps"], [], None),
    ("Arm curl machine", "upper", "strength", "gym", ["biceps"], ["forearms"], None),
    ("Sit-ups", "core", "strength", "home", ["abs"], ["hip_flexors"], None),
    ("Abdominal machine", "core", "strength", "gym", ["abs"], ["hip_flexors"], None),
    ("Captain's Chair Leg Raise", "core", "strength", "gym", ["abs", "hip_flexors"], [], None),
    ("Leg raise", "core", "strength", "gym", ["abs", "hip_flexors"], [], None),
    ("Leg Raise unweighted", "core", "strength", "both", ["abs", "hip_flexors"], [], None),
    (
        "Back Extension Machine",
        "core",
        "strength",
        "gym",
        ["lower_back"],
        ["glutes", "hamstrings"],
        None,
    ),
    ("Hack squat", "lower", "strength", "gym", ["quads"], ["glutes", "adductors"], None),
    (
        "Leg press",
        "lower",
        "strength",
        "gym",
        ["quads", "glutes"],
        ["hamstrings", "adductors"],
        None,
    ),
    ("Leg extension", "lower", "strength", "gym", ["quads"], [], None),
    ("Leg curl", "lower", "strength", "gym", ["hamstrings"], ["calves"], None),
    ("Dumbbell squat", "lower", "strength", "both", ["quads", "glutes"], ["adductors"], None),
    (
        "Romanian Dead Lift",
        "lower",
        "strength",
        "both",
        ["hamstrings", "glutes"],
        ["lower_back", "forearms"],
        None,
    ),
    (
        "Kettle Bell Swing",
        "lower",
        "strength",
        "both",
        ["glutes", "hamstrings"],
        ["lower_back", "abs"],
        None,
    ),
    # Cardio: primary = muscles whose "last trained" date it updates; scored in minutes.
    ("Hiking", "full", "cardio", "both", ["quads", "glutes", "calves"], [], "timed"),
    ("Treadmill", "lower", "cardio", "gym", ["calves"], [], "timed"),
    ("StairMaster", "lower", "cardio", "gym", ["quads", "glutes", "calves"], [], "timed"),
]

ROWING = ("Rowing machine", "full", "cardio", "home", ["upper_back", "quads"], [], "timed")
SEATED_ROW = (
    "Row Machine",
    "upper",
    "strength",
    "gym",
    ["upper_back"],
    ["biceps", "rear_delts"],
    None,
)
BENCH_TAGS = RETAG[2]


def _log_count(conn, name: str) -> int | None:
    """Logs against the named exercise, or None if it isn't in the catalog."""
    row = conn.execute(
        sa.text(
            "SELECT e.id, count(l.id) FROM exercises e "
            "LEFT JOIN exercise_logs l ON l.exercise_id = e.id "
            "WHERE lower(e.name) = lower(:name) GROUP BY e.id"
        ),
        {"name": name},
    ).first()
    return None if row is None else row[1]


def _exists(conn, name: str) -> bool:
    return _log_count(conn, name) is not None


def _retag(conn, match_name: str, entry, rename: bool = False) -> None:
    name, region, modality, location, primary, secondary, scoring = entry
    conn.execute(
        sa.text(
            "UPDATE exercises SET region = :region, modality = :modality, "
            "location = :location, primary_muscles = CAST(:primary AS jsonb), "
            "secondary_muscles = CAST(:secondary AS jsonb), "
            "scoring_type = COALESCE(:scoring, scoring_type)"
            + (", name = :new_name" if rename else "")
            + " WHERE lower(name) = lower(:match)"
        ),
        {
            "region": region,
            "modality": modality,
            "location": location,
            "primary": json.dumps(primary),
            "secondary": json.dumps(secondary),
            "scoring": scoring,
            "new_name": name,
            "match": match_name,
        },
    )


def upgrade() -> None:
    op.add_column("exercises", sa.Column("region", sa.String(16), nullable=True))
    op.add_column("exercises", sa.Column("modality", sa.String(16), nullable=True))
    op.add_column("exercises", sa.Column("location", sa.String(8), nullable=True))
    op.add_column(
        "exercises",
        sa.Column("primary_muscles", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "exercises",
        sa.Column("secondary_muscles", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("exercise_logs", sa.Column("body_weight_used", sa.Numeric(5, 2), nullable=True))

    conn = op.get_bind()

    # Defaults for every row (covers exercises not in the re-tag table).
    conn.execute(
        sa.text(
            "UPDATE exercises SET "
            "region = CASE WHEN body_group = 'cardio' THEN 'full' ELSE body_group END, "
            "modality = CASE WHEN body_group = 'cardio' OR scoring_type = 'distance' "
            "THEN 'cardio' ELSE 'strength' END, "
            "location = 'both'"
        )
    )

    for entry in RETAG:
        _retag(conn, entry[0], entry)

    # The catalog's "Row Machine" is the home cardio rowing machine. Repurpose it
    # only if nothing was logged against it as a weighted row; otherwise keep it as
    # the gym seated row and add the rowing machine alongside.
    row_logs = _log_count(conn, "Row Machine")
    if row_logs is not None:
        if row_logs == 0 and not _exists(conn, ROWING[0]):
            _retag(conn, "Row Machine", ROWING, rename=True)
        else:
            _retag(conn, "Row Machine", SEATED_ROW)
            if not _exists(conn, ROWING[0]):
                conn.execute(
                    sa.text(
                        "INSERT INTO exercises (name, region, modality, location, "
                        "primary_muscles, secondary_muscles, scoring_type, bodyweight_fraction) "
                        "VALUES (:name, :region, :modality, :location, "
                        "CAST(:primary AS jsonb), CAST(:secondary AS jsonb), :scoring, 1.000)"
                    ),
                    {
                        "name": ROWING[0],
                        "region": ROWING[1],
                        "modality": ROWING[2],
                        "location": ROWING[3],
                        "primary": json.dumps(ROWING[4]),
                        "secondary": json.dumps(ROWING[5]),
                        "scoring": ROWING[6],
                    },
                )

    # "Flat Dumbbell Press" duplicates "Dumbbell bench press": drop it if unused.
    flat_logs = _log_count(conn, "Flat Dumbbell Press")
    if flat_logs == 0:
        conn.execute(sa.text("DELETE FROM exercises WHERE lower(name) = 'flat dumbbell press'"))
    elif flat_logs is not None:
        _retag(conn, "Flat Dumbbell Press", BENCH_TAGS)

    # Score for every timed exercise is minutes. Logs without a duration score 0
    # (still sessions for recency; no estimating from distance).
    conn.execute(
        sa.text(
            "UPDATE exercise_logs SET work_score = COALESCE(duration_minutes, 0) "
            "WHERE exercise_id IN (SELECT id FROM exercises WHERE scoring_type = 'timed')"
        )
    )

    # Backfill with each user's current weight: an approximation, but the best
    # available (body weight was never versioned).
    conn.execute(
        sa.text(
            "UPDATE exercise_logs l SET body_weight_used = u.body_weight "
            "FROM users u WHERE u.id = l.user_id"
        )
    )

    op.alter_column("exercises", "region", nullable=False)
    op.alter_column("exercises", "modality", nullable=False)
    op.alter_column("exercises", "location", nullable=False)
    op.drop_column("exercises", "body_group")
    op.drop_column("exercises", "muscle_groups")


def downgrade() -> None:
    """Approximate: restores the old columns from the new ones. Muscle tags come
    back as the vocabulary names, timed exercises go back to distance scoring
    (re-scored from distance x body_weight_used), and the Row Machine rename and
    Flat Dumbbell Press deletion are not undone."""
    op.add_column("exercises", sa.Column("body_group", sa.String(16), nullable=True))
    op.add_column(
        "exercises",
        sa.Column("muscle_groups", JSONB(), nullable=False, server_default="[]"),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE exercises SET "
            "body_group = CASE WHEN modality = 'cardio' THEN 'cardio' "
            "WHEN region = 'full' THEN 'upper' ELSE region END, "
            "muscle_groups = primary_muscles || secondary_muscles"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE exercise_logs SET work_score = COALESCE(distance_km * body_weight_used, 0) "
            "WHERE exercise_id IN (SELECT id FROM exercises WHERE scoring_type = 'timed')"
        )
    )
    conn.execute(
        sa.text("UPDATE exercises SET scoring_type = 'distance' WHERE scoring_type = 'timed'")
    )
    op.alter_column("exercises", "body_group", nullable=False)
    op.drop_column("exercise_logs", "body_weight_used")
    op.drop_column("exercises", "secondary_muscles")
    op.drop_column("exercises", "primary_muscles")
    op.drop_column("exercises", "location")
    op.drop_column("exercises", "modality")
    op.drop_column("exercises", "region")
