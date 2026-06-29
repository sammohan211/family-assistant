"""lessons: parent-curated home-learning plan (lesson / objectives / resources / test)

Revision ID: 0023_lessons
Revises: 0022_drop_horoscope_readings
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_lessons"
down_revision: str | None = "0022_drop_horoscope_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("subject", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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

    op.create_table(
        "learning_objectives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lessons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_learning_objectives_lesson_id", "learning_objectives", ["lesson_id"])

    op.create_table(
        "lesson_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lessons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "objective_id",
            sa.Integer(),
            sa.ForeignKey("learning_objectives.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_lesson_resources_lesson_id", "lesson_resources", ["lesson_id"])
    op.create_index("ix_lesson_resources_objective_id", "lesson_resources", ["objective_id"])

    op.create_table(
        "lesson_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lessons.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    op.create_index("ix_lesson_tests_lesson_id", "lesson_tests", ["lesson_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_lesson_tests_lesson_id", table_name="lesson_tests")
    op.drop_table("lesson_tests")
    op.drop_index("ix_lesson_resources_objective_id", table_name="lesson_resources")
    op.drop_index("ix_lesson_resources_lesson_id", table_name="lesson_resources")
    op.drop_table("lesson_resources")
    op.drop_index("ix_learning_objectives_lesson_id", table_name="learning_objectives")
    op.drop_table("learning_objectives")
    op.drop_table("lessons")
