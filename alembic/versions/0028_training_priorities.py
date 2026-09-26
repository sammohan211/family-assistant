"""exercise: weekly training priorities

PRD §10.16 step 3. One row per (user, ISO week) holding the dashboard card's
priorities, overwritten on each Refresh.

Revision ID: 0028_training_priorities
Revises: 0027_training_week_summaries
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0028_training_priorities"
down_revision: str | None = "0027_training_week_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_priorities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "week_start", name="uq_training_priorities_user_week"),
    )
    op.create_index("ix_training_priorities_user_id", "training_priorities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_training_priorities_user_id", table_name="training_priorities")
    op.drop_table("training_priorities")
