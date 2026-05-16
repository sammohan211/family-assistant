"""Schema-parity smoke test: models must match the Alembic migration head.

The `engine` fixture runs `alembic upgrade head` against the test database, so
this test compares the live DB schema against `Base.metadata`. Any drift —
a new column on a model with no corresponding migration, a renamed table, a
dropped index — surfaces here.
"""

from sqlalchemy.engine import Engine

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from family_assistant.db import Base


def test_models_match_migration_head(engine: Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], (
        "Drift between SQLAlchemy models and Alembic migration head. "
        "Add a migration for the changes below:\n"
        f"{diff}"
    )
