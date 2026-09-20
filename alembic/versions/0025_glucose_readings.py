"""glucose: per-user blood glucose readings, owner-restricted

Revision ID: 0025_glucose_readings
Revises: 0024_projects
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_glucose_readings"
down_revision: str | None = "0024_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "glucose_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reading_time", sa.Time(), nullable=True),
        sa.Column("value_mg_dl", sa.Integer(), nullable=False),
        sa.Column("context", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_glucose_readings_user_id", "glucose_readings", ["user_id"])
    op.create_index("ix_glucose_readings_date", "glucose_readings", ["date"])


def downgrade() -> None:
    op.drop_index("ix_glucose_readings_date", table_name="glucose_readings")
    op.drop_index("ix_glucose_readings_user_id", table_name="glucose_readings")
    op.drop_table("glucose_readings")
