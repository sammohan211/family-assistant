"""household tasks: shared recurring chores + completion history

Revision ID: 0020_household_tasks
Revises: 0019_hikes
Create Date: 2026-06-07

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_household_tasks"
down_revision: str | None = "0019_hikes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("frequency_unit", sa.String(8), nullable=False),
        sa.Column("frequency_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_completed_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_household_tasks_assignee_id", "household_tasks", ["assignee_id"])
    op.create_index("ix_household_tasks_next_due_date", "household_tasks", ["next_due_date"])

    op.create_table(
        "household_task_completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("household_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_on", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_household_task_completions_task_id", "household_task_completions", ["task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_household_task_completions_task_id", table_name="household_task_completions")
    op.drop_table("household_task_completions")
    op.drop_index("ix_household_tasks_next_due_date", table_name="household_tasks")
    op.drop_index("ix_household_tasks_assignee_id", table_name="household_tasks")
    op.drop_table("household_tasks")
