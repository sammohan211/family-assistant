"""exercise entries

Revision ID: 0006_exercise_entries
Revises: 0005_lunch_plan_entries
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_exercise_entries"
down_revision: str | None = "0005_lunch_plan_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("ix_exercise_entries_user_id", table_name="exercise_entries")
    op.drop_table("exercise_entries")
