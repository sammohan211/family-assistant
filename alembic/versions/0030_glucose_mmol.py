"""glucose: store readings in mmol/L (Canadian units) instead of mg/dL

Existing readings are converted in place (mg/dL / 18, rounded to 0.1 mmol/L)
and the column is renamed to match. Downgrade converts back (x 18, rounded to
a whole mg/dL), so a round trip can shift a reading by up to 1 mg/dL.

Revision ID: 0030_glucose_mmol
Revises: 0029_grocery_on_hand
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_glucose_mmol"
down_revision: str | None = "0029_grocery_on_hand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "glucose_readings",
        "value_mg_dl",
        existing_type=sa.Integer(),
        type_=sa.Numeric(4, 1),
        existing_nullable=False,
        postgresql_using="round(value_mg_dl / 18.0, 1)",
    )
    op.alter_column("glucose_readings", "value_mg_dl", new_column_name="value_mmol_l")


def downgrade() -> None:
    op.alter_column("glucose_readings", "value_mmol_l", new_column_name="value_mg_dl")
    op.alter_column(
        "glucose_readings",
        "value_mg_dl",
        existing_type=sa.Numeric(4, 1),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="round(value_mg_dl * 18)::integer",
    )
