"""grocery: on-hand location (kitchen | freezer) and the used_up status

Purchased items are now "on hand" until marked used up. Existing purchased
rows default to the kitchen.

Revision ID: 0029_grocery_on_hand
Revises: 0028_training_priorities
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_grocery_on_hand"
down_revision: str | None = "0028_training_priorities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "grocery_items",
        sa.Column("location", sa.String(20), nullable=False, server_default="kitchen"),
    )


def downgrade() -> None:
    # used_up has no older equivalent; purchased is the closest.
    op.execute("UPDATE grocery_items SET status = 'purchased' WHERE status = 'used_up'")
    op.drop_column("grocery_items", "location")
