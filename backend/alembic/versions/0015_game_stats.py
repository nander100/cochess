"""Per-game dashboard numbers (SPEC_V3 §8.1, PLAN_V3 adjustment 6).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_stats",
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("accuracy", sa.Float()),
        sa.Column("accuracy_opening", sa.Float()),
        sa.Column("accuracy_middlegame", sa.Float()),
        sa.Column("accuracy_endgame", sa.Float()),
        sa.Column("moments_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_game_stats_user_id", "game_stats", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_game_stats_user_id", table_name="game_stats")
    op.drop_table("game_stats")
