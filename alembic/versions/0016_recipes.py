"""recipes: household-shared recipe catalog for meal planning

Revision ID: 0016_recipes
Revises: 0015_interaction_traces
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0016_recipes"
down_revision: str | None = "0015_interaction_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=140), nullable=False, unique=True),
        sa.Column("meal_type", sa.String(length=20), nullable=False),
        sa.Column("ingredients", JSONB(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("protein_g", sa.Integer(), nullable=True),
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


def downgrade() -> None:
    op.drop_table("recipes")
