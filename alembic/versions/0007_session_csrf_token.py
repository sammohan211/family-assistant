"""session csrf token

Revision ID: 0007_session_csrf_token
Revises: 0006_exercise_entries
Create Date: 2026-05-16

"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_session_csrf_token"
down_revision: str | None = "0006_exercise_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("csrf_token", sa.String(length=64), nullable=True),
    )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT token FROM sessions WHERE csrf_token IS NULL")).all()
    for (token,) in rows:
        bind.execute(
            sa.text("UPDATE sessions SET csrf_token = :csrf WHERE token = :token"),
            {"csrf": secrets.token_urlsafe(32), "token": token},
        )
    op.alter_column("sessions", "csrf_token", nullable=False)


def downgrade() -> None:
    op.drop_column("sessions", "csrf_token")
