"""horoscope: cached household-shared readings per system and period

Revision ID: 0021_horoscope_readings
Revises: 0020_household_tasks
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_horoscope_readings"
down_revision: str | None = "0020_household_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "horoscope_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("system", sa.String(16), nullable=False),
        sa.Column("period_type", sa.String(8), nullable=False),
        sa.Column("period_key", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("system", "period_type", "period_key", name="uq_horoscope_period"),
    )
    op.create_index("ix_horoscope_readings_period_type", "horoscope_readings", ["period_type"])
    op.create_index("ix_horoscope_readings_period_key", "horoscope_readings", ["period_key"])


def downgrade() -> None:
    op.drop_index("ix_horoscope_readings_period_key", table_name="horoscope_readings")
    op.drop_index("ix_horoscope_readings_period_type", table_name="horoscope_readings")
    op.drop_table("horoscope_readings")
