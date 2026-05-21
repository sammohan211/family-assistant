"""interaction_traces

Revision ID: 0015_interaction_traces
Revises: 0014_grocery_quantity_decimal
Create Date: 2026-05-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_interaction_traces"
down_revision: str | None = "0014_grocery_quantity_decimal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interaction_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "interaction_id",
            sa.Integer(),
            sa.ForeignKey("assistant_interactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ts_ms", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_interaction_traces_interaction_ts",
        "interaction_traces",
        ["interaction_id", "ts_ms"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interaction_traces_interaction_ts",
        table_name="interaction_traces",
    )
    op.drop_table("interaction_traces")
