"""assistant_interactions: add reply column

Revision ID: 0012_assistant_reply
Revises: 0011_assistant_interactions
Create Date: 2026-05-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_assistant_reply"
down_revision: str | None = "0011_assistant_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_interactions",
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("assistant_interactions", "reply")
