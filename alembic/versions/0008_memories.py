"""memories

Revision ID: 0008_memories
Revises: 0007_session_csrf_token
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_memories"
down_revision: str | None = "0007_session_csrf_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("memory_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_hard_restriction",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
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
    op.create_index("ix_memories_subject", "memories", ["subject_type", "subject_id"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])


def downgrade() -> None:
    op.drop_index("ix_memories_memory_type", table_name="memories")
    op.drop_index("ix_memories_subject", table_name="memories")
    op.drop_table("memories")
