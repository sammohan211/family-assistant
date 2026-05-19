"""exercise: catalog + per-session log with work_score; user.body_weight

Revision ID: 0013_exercise_redesign
Revises: 0012_assistant_reply
Create Date: 2026-05-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0013_exercise_redesign"
down_revision: str | None = "0012_assistant_reply"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_exercise_entries_user_id", table_name="exercise_entries")
    op.drop_table("exercise_entries")

    op.add_column("users", sa.Column("body_weight", sa.Numeric(5, 2), nullable=True))

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("body_group", sa.String(length=16), nullable=False),
        sa.Column("muscle_groups", JSONB(), nullable=False, server_default="[]"),
        sa.Column("scoring_type", sa.String(length=24), nullable=False),
        sa.Column(
            "bodyweight_fraction",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="1.000",
        ),
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

    op.create_table(
        "exercise_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exercise_id",
            sa.Integer(),
            sa.ForeignKey("exercises.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Numeric(6, 2), nullable=True),
        sa.Column("distance_km", sa.Numeric(7, 3), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "work_score",
            sa.Numeric(12, 3),
            nullable=False,
            server_default="0",
        ),
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
    op.create_index("ix_exercise_logs_user_id", "exercise_logs", ["user_id"])
    op.create_index("ix_exercise_logs_exercise_id", "exercise_logs", ["exercise_id"])
    op.create_index("ix_exercise_logs_date", "exercise_logs", ["date"])


def downgrade() -> None:
    op.drop_index("ix_exercise_logs_date", table_name="exercise_logs")
    op.drop_index("ix_exercise_logs_exercise_id", table_name="exercise_logs")
    op.drop_index("ix_exercise_logs_user_id", table_name="exercise_logs")
    op.drop_table("exercise_logs")
    op.drop_table("exercises")

    op.drop_column("users", "body_weight")

    op.create_table(
        "exercise_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("activity_type", sa.String(length=80), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
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
    op.create_index("ix_exercise_entries_user_id", "exercise_entries", ["user_id"])
