"""meal plan entries

Revision ID: 0004_meal_plan_entries
Revises: 0003_grocery_items
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_meal_plan_entries"
down_revision: str | None = "0003_grocery_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_plan_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
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
    op.create_index(
        "ix_meal_plan_entries_created_by_user_id",
        "meal_plan_entries",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_meal_plan_entries_created_by_user_id", table_name="meal_plan_entries")
    op.drop_table("meal_plan_entries")
