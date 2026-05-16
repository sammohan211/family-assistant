"""assistant_interactions

Revision ID: 0011_assistant_interactions
Revises: 0010_user_name
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_assistant_interactions"
down_revision: str | None = "0010_user_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("parsed_intent", postgresql.JSONB(), nullable=True),
        sa.Column("parsed_entities", postgresql.JSONB(), nullable=True),
        sa.Column(
            "proposed_tool_calls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confirmation_status", sa.String(length=20), nullable=False),
        sa.Column(
            "executed_tool_calls",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "affected_record_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_assistant_interactions_user_created",
        "assistant_interactions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_interactions_user_created",
        table_name="assistant_interactions",
    )
    op.drop_table("assistant_interactions")
