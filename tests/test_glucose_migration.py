"""Data test for migration 0030 (glucose readings mg/dL -> mmol/L).

Steps the shared test database back to 0029, inserts mg/dL readings, upgrades
to head and checks the conversion, then downgrades again to check the way
back. The ``finally`` block deletes the rows and puts the schema back at head,
so other tests still see an empty database.
"""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
BEFORE = "0029_grocery_on_hand"
EMAIL = "migration-0030@example.com"


@pytest.fixture
def alembic_cfg(engine: Engine) -> Iterator[Config]:
    cfg = Config(str(ALEMBIC_INI))
    url = engine.url.render_as_string(hide_password=False)
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(cfg, BEFORE)
    try:
        yield cfg
    finally:
        # The cascade from users removes the readings, whichever side of 0030
        # the schema ended up on.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": EMAIL})
        command.upgrade(cfg, "head")


def test_upgrade_converts_mg_dl_to_mmol_l(engine: Engine, alembic_cfg: Config) -> None:
    with engine.begin() as conn:
        user_id = conn.execute(
            text(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES ('M', :email, 'x') RETURNING id"
            ),
            {"email": EMAIL},
        ).scalar_one()
        for value in (95, 100, 126, 200):
            conn.execute(
                text(
                    "INSERT INTO glucose_readings (user_id, date, value_mg_dl, context) "
                    "VALUES (:uid, '2026-11-01', :value, 'fasting')"
                ),
                {"uid": user_id, "value": value},
            )

    command.upgrade(alembic_cfg, "0030_glucose_mmol")
    with engine.connect() as conn:
        values = conn.execute(
            text("SELECT value_mmol_l FROM glucose_readings WHERE user_id = :uid ORDER BY id"),
            {"uid": user_id},
        ).scalars().all()
    assert values == [Decimal("5.3"), Decimal("5.6"), Decimal("7.0"), Decimal("11.1")]

    command.downgrade(alembic_cfg, BEFORE)
    with engine.connect() as conn:
        values = conn.execute(
            text("SELECT value_mg_dl FROM glucose_readings WHERE user_id = :uid ORDER BY id"),
            {"uid": user_id},
        ).scalars().all()
    # 0.1 mmol/L is 1.8 mg/dL, so the round trip can be off by one.
    assert values == [95, 101, 126, 200]
