"""lunch_plan items: json -> jsonb

Revision ID: 0009_lunch_plan_items_jsonb
Revises: 0008_memories
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_lunch_plan_items_jsonb"
down_revision: str | None = "0008_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "lunch_plan_entries",
        "items",
        type_=postgresql.JSONB(),
        existing_type=sa.JSON(),
        existing_nullable=False,
        postgresql_using="items::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "lunch_plan_entries",
        "items",
        type_=sa.JSON(),
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
        postgresql_using="items::json",
    )
