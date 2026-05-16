"""lunch plan entries

Revision ID: 0005_lunch_plan_entries
Revises: 0004_meal_plan_entries
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_lunch_plan_entries"
down_revision: str | None = "0004_meal_plan_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lunch_plan_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "family_member_id",
            sa.Integer(),
            sa.ForeignKey("family_members.id"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("packed_status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
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
    op.create_index(
        "ix_lunch_plan_entries_family_member_id",
        "lunch_plan_entries",
        ["family_member_id"],
    )
    op.create_index(
        "ix_lunch_plan_entries_created_by_user_id",
        "lunch_plan_entries",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lunch_plan_entries_created_by_user_id", table_name="lunch_plan_entries")
    op.drop_index("ix_lunch_plan_entries_family_member_id", table_name="lunch_plan_entries")
    op.drop_table("lunch_plan_entries")
