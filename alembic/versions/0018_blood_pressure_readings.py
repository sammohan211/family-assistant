"""bp: per-user blood pressure readings with computed MAP

Revision ID: 0018_blood_pressure_readings
Revises: 0017_recipe_instructions
Create Date: 2026-06-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_blood_pressure_readings"
down_revision: str | None = "0017_recipe_instructions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blood_pressure_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reading_time", sa.Time(), nullable=True),
        sa.Column("systolic", sa.Integer(), nullable=False),
        sa.Column("diastolic", sa.Integer(), nullable=False),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("map_value", sa.Numeric(6, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_blood_pressure_readings_user_id", "blood_pressure_readings", ["user_id"])
    op.create_index("ix_blood_pressure_readings_date", "blood_pressure_readings", ["date"])


def downgrade() -> None:
    op.drop_index("ix_blood_pressure_readings_date", table_name="blood_pressure_readings")
    op.drop_index("ix_blood_pressure_readings_user_id", table_name="blood_pressure_readings")
    op.drop_table("blood_pressure_readings")
