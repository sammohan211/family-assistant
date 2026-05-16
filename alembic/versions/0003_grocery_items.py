"""grocery items

Revision ID: 0003_grocery_items
Revises: 0002_family_members
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_grocery_items"
down_revision: str | None = "0002_family_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grocery_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("added_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purchased_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
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
    op.create_index("ix_grocery_items_added_by_user_id", "grocery_items", ["added_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_grocery_items_added_by_user_id", table_name="grocery_items")
    op.drop_table("grocery_items")
