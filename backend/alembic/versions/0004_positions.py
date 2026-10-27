"""Positions for v2 chat (SPEC_V2 §6, §12): engine results findable by position, and the board
position each chat message and pending tool call came from.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("engine_results") as batch:
        batch.add_column(sa.Column("position_key", sa.String(100), nullable=True))
    # The FEN without its move counters; the same rule as app.analysis.paths.position_key, kept
    # here so this migration never changes when app code does.
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, fen FROM engine_results")).all()
    for row_id, fen in rows:
        connection.execute(
            sa.text("UPDATE engine_results SET position_key = :key WHERE id = :id"),
            {"key": " ".join(fen.split()[:4]), "id": row_id},
        )
    with op.batch_alter_table("engine_results") as batch:
        batch.alter_column("position_key", existing_type=sa.String(100), nullable=False)
        batch.create_index("ix_engine_results_game_id_position_key", ["game_id", "position_key"])

    for table in ("chat_messages", "pending_tool_calls"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("path_uci", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in ("pending_tool_calls", "chat_messages"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("path_uci")
    with op.batch_alter_table("engine_results") as batch:
        batch.drop_index("ix_engine_results_game_id_position_key")
        batch.drop_column("position_key")
