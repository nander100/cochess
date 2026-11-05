"""Saved variations (SPEC_V3 §5.1).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_variations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_path", sa.JSON(), nullable=False),
        sa.Column("moves", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_game_variations_game_id_position", "game_variations", ["game_id", "position"]
    )
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("variations_saved_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_column("variations_saved_at")
    op.drop_index("ix_game_variations_game_id_position", table_name="game_variations")
    op.drop_table("game_variations")
