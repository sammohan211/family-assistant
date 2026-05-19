"""grocery: quantity Integer -> Numeric(10, 3)

Revision ID: 0014_grocery_quantity_decimal
Revises: 0013_exercise_redesign
Create Date: 2026-05-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_grocery_quantity_decimal"
down_revision: str | None = "0013_exercise_redesign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "grocery_items",
        "quantity",
        existing_type=sa.Integer(),
        type_=sa.Numeric(10, 3),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "grocery_items",
        "quantity",
        existing_type=sa.Numeric(10, 3),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="quantity::integer",
    )
