"""Critical-moment progress (SPEC_V2 §8.2, §12).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moment_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("moment_index", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.Column("revealed", sa.Boolean(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("leaks", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_id", "moment_index"),
    )
    op.create_index("ix_moment_progress_user_id", "moment_progress", ["user_id"])
    op.create_index("ix_moment_progress_game_id", "moment_progress", ["game_id"])


def downgrade() -> None:
    op.drop_table("moment_progress")
