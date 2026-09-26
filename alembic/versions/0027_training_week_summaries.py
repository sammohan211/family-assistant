"""exercise: stored weekly training summaries

PRD §10.16 step 2. One JSONB snapshot per (user, completed ISO week), built
lazily and deleted when that week's logs or the catalog change.

Revision ID: 0027_training_week_summaries
Revises: 0026_exercise_catalog_remodel
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0027_training_week_summaries"
down_revision: str | None = "0026_exercise_catalog_remodel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_week_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "week_start", name="uq_training_week_summaries_user_week"),
    )
    op.create_index("ix_training_week_summaries_user_id", "training_week_summaries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_training_week_summaries_user_id", table_name="training_week_summaries")
    op.drop_table("training_week_summaries")
