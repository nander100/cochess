"""Cached line walkthroughs (SPEC_V3 §7.2, §11.2).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "walkthroughs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("start_path", sa.JSON(), nullable=False),
        sa.Column("start_fen", sa.String(100), nullable=False),
        sa.Column("line_key", sa.String(64), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "start_fen", "line_key", name="uq_walkthroughs_user_line"),
    )
    op.create_index("ix_walkthroughs_user_id", "walkthroughs", ["user_id"])
    op.create_index("ix_walkthroughs_game_id", "walkthroughs", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_walkthroughs_game_id", table_name="walkthroughs")
    op.drop_index("ix_walkthroughs_user_id", table_name="walkthroughs")
    op.drop_table("walkthroughs")
