"""recipes: add nullable instructions ("how to make") column

Revision ID: 0017_recipe_instructions
Revises: 0016_recipes
Create Date: 2026-06-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_recipe_instructions"
down_revision: str | None = "0016_recipes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "instructions")
