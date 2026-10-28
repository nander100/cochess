"""Theme facts and tendency snapshots (SPEC_V2 §9, §12).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_theme_facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("theme", sa.String(32), nullable=False),
        sa.Column("subtype", sa.String(32), nullable=True),
        sa.Column("ply", sa.Integer(), nullable=True),
        sa.Column("move_number", sa.Integer(), nullable=True),
        sa.Column("move_san", sa.String(10), nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("phase", sa.String(10), nullable=True),
        sa.Column("user_color", sa.String(5), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_game_theme_facts_user_id_theme", "game_theme_facts", ["user_id", "theme"])
    op.create_index("ix_game_theme_facts_game_id", "game_theme_facts", ["game_id"])
    op.create_table(
        "tendency_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("games_analyzed", sa.Integer(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tendency_snapshots_user_id_created_at", "tendency_snapshots", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("tendency_snapshots")
    op.drop_table("game_theme_facts")
