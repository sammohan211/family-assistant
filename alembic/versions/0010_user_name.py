"""user name

Revision ID: 0010_user_name
Revises: 0009_lunch_plan_items_jsonb
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_user_name"
down_revision: str | None = "0009_lunch_plan_items_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(length=120), nullable=True))
    op.execute("UPDATE users SET name = split_part(email, '@', 1) WHERE name IS NULL")
    op.alter_column("users", "name", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "name")
