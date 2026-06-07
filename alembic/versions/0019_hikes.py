"""hike: per-user Bruce Trail segment log with computed speed

Revision ID: 0019_hikes
Revises: 0018_blood_pressure_readings
Create Date: 2026-06-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_hikes"
down_revision: str | None = "0018_blood_pressure_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hikes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("section", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_location", sa.Text(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_location", sa.Text(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("distance_km", sa.Numeric(7, 3), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("speed_kmh", sa.Numeric(6, 3), nullable=False),
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
    op.create_index("ix_hikes_user_id", "hikes", ["user_id"])
    op.create_index("ix_hikes_date", "hikes", ["date"])


def downgrade() -> None:
    op.drop_index("ix_hikes_date", table_name="hikes")
    op.drop_index("ix_hikes_user_id", table_name="hikes")
    op.drop_table("hikes")
