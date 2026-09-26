"""Data tests for migration 0026 (exercise catalog re-model, PRD §10.16).

Each test steps the shared test database back to 0025, inserts an old-format
catalog + logs, upgrades to head, and checks the re-tag. The ``finally`` blocks
put the schema back at head and delete the rows, so other tests still see an
empty database.
"""

import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
BEFORE = "0025_glucose_readings"
EMAIL = "migration-0026@example.com"


@pytest.fixture
def alembic_cfg(engine: Engine) -> Iterator[Config]:
    cfg = Config(str(ALEMBIC_INI))
    url = engine.url.render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(cfg, BEFORE)
    try:
        yield cfg
    finally:
        # Delete rows first: if the upgrade under test failed, the schema is still
        # at 0025 and the upgrade below would fail again on the same data.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM exercise_logs WHERE user_id IN "
                    "(SELECT id FROM users WHERE email = :email)"
                ),
                {"email": EMAIL},
            )
            conn.execute(text("DELETE FROM exercises"))
            conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": EMAIL})
        command.upgrade(cfg, "head")


def _seed_old_catalog(conn: Connection, *, row_machine_logged: bool) -> None:
    user_id = conn.execute(
        text(
            "INSERT INTO users (name, email, password_hash, body_weight) "
            "VALUES ('M', :email, 'x', 180) RETURNING id"
        ),
        {"email": EMAIL},
    ).scalar_one()
    ids: dict[str, int] = {}
    for name, body_group, scoring in [
        ("Lat pulldown", "upper", "weighted"),
        ("Hiking", "cardio", "distance"),
        ("Treadmill", "cardio", "distance"),
        ("Row Machine", "upper", "weighted"),
        ("Flat Dumbbell Press", "upper", "weighted"),
        ("Jump rope", "cardio", "distance"),  # not in the re-tag table
        ("Mystery curl", "upper", "weighted"),  # not in the re-tag table
    ]:
        ids[name] = conn.execute(
            text(
                "INSERT INTO exercises (name, body_group, muscle_groups, scoring_type) "
                "VALUES (:name, :bg, CAST(:mg AS jsonb), :scoring) RETURNING id"
            ),
            {"name": name, "bg": body_group, "mg": json.dumps(["legacy tag"]), "scoring": scoring},
        ).scalar_one()
    logs = [
        ("Lat pulldown", 3, 10, 88, None, None, 2640),
        ("Hiking", None, None, None, 4.88, 195, 878.4),
        ("Treadmill", None, None, None, 1.4, None, 252),
    ]
    if row_machine_logged:
        logs.append(("Row Machine", 3, 10, 80, None, None, 2400))
    for name, sets, reps, weight, km, minutes, score in logs:
        conn.execute(
            text(
                "INSERT INTO exercise_logs (user_id, exercise_id, date, sets, reps, weight, "
                "distance_km, duration_minutes, work_score) "
                "VALUES (:u, :e, '2026-09-01', :sets, :reps, :weight, :km, :minutes, :score)"
            ),
            {
                "u": user_id,
                "e": ids[name],
                "sets": sets,
                "reps": reps,
                "weight": weight,
                "km": km,
                "minutes": minutes,
                "score": score,
            },
        )


def _exercise(conn: Connection, name: str) -> dict | None:
    row = (
        conn.execute(
            text(
                "SELECT region, modality, location, primary_muscles, secondary_muscles, "
                "scoring_type FROM exercises WHERE name = :name"
            ),
            {"name": name},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _log(conn: Connection, name: str) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT l.work_score, l.body_weight_used FROM exercise_logs l "
                "JOIN exercises e ON e.id = l.exercise_id WHERE e.name = :name"
            ),
            {"name": name},
        )
        .mappings()
        .one()
    )


def test_upgrade_retags_catalog_and_rescores_cardio(engine: Engine, alembic_cfg: Config) -> None:
    with engine.begin() as conn:
        _seed_old_catalog(conn, row_machine_logged=False)

    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        assert _exercise(conn, "Lat pulldown") == {
            "region": "upper",
            "modality": "strength",
            "location": "gym",
            "primary_muscles": ["upper_back"],
            "secondary_muscles": ["biceps", "rear_delts"],
            "scoring_type": "weighted",
        }
        # Strength scores are untouched; every log gets the user's weight.
        assert _log(conn, "Lat pulldown") == {
            "work_score": Decimal("2640.000"),
            "body_weight_used": Decimal("180.00"),
        }

        hiking = _exercise(conn, "Hiking")
        assert hiking is not None
        assert (hiking["region"], hiking["modality"], hiking["scoring_type"]) == (
            "full",
            "cardio",
            "timed",
        )
        assert hiking["primary_muscles"] == ["quads", "glutes", "calves"]
        assert _log(conn, "Hiking")["work_score"] == Decimal("195")
        assert _log(conn, "Treadmill")["work_score"] == Decimal("0")  # no duration logged

        # Unlogged "Row Machine" becomes the home rowing machine; the duplicate press goes.
        assert _exercise(conn, "Row Machine") is None
        rowing = _exercise(conn, "Rowing machine")
        assert rowing is not None
        assert (rowing["location"], rowing["scoring_type"]) == ("home", "timed")
        assert _exercise(conn, "Flat Dumbbell Press") is None

        # Exercises outside the table get defaults and no muscles (flagged in the UI).
        assert _exercise(conn, "Jump rope") == {
            "region": "full",
            "modality": "cardio",
            "location": "both",
            "primary_muscles": [],
            "secondary_muscles": [],
            "scoring_type": "distance",
        }
        mystery = _exercise(conn, "Mystery curl")
        assert mystery is not None
        assert (mystery["region"], mystery["modality"]) == ("upper", "strength")


def test_upgrade_keeps_logged_row_machine_and_adds_rowing(
    engine: Engine, alembic_cfg: Config
) -> None:
    with engine.begin() as conn:
        _seed_old_catalog(conn, row_machine_logged=True)

    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        row = _exercise(conn, "Row Machine")
        assert row is not None
        assert (row["modality"], row["scoring_type"]) == ("strength", "weighted")
        assert row["primary_muscles"] == ["upper_back"]
        assert _log(conn, "Row Machine")["work_score"] == Decimal("2400.000")
        rowing = _exercise(conn, "Rowing machine")
        assert rowing is not None
        assert rowing["modality"] == "cardio"


def test_downgrade_restores_old_columns(engine: Engine, alembic_cfg: Config) -> None:
    with engine.begin() as conn:
        _seed_old_catalog(conn, row_machine_logged=False)
    command.upgrade(alembic_cfg, "head")

    command.downgrade(alembic_cfg, BEFORE)

    with engine.connect() as conn:
        hiking = conn.execute(
            text(
                "SELECT e.body_group, e.scoring_type, l.work_score FROM exercises e "
                "JOIN exercise_logs l ON l.exercise_id = e.id WHERE e.name = 'Hiking'"
            )
        ).one()
        assert hiking.body_group == "cardio"
        assert hiking.scoring_type == "distance"
        assert hiking.work_score == Decimal("878.400")  # 4.88 km x 180
        muscles = conn.execute(
            text("SELECT muscle_groups FROM exercises WHERE name = 'Lat pulldown'")
        ).scalar_one()
        assert muscles == ["upper_back", "biceps", "rear_delts"]
