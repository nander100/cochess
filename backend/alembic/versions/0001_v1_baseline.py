"""v1 baseline: the schema v1 created with create_all (tag v1).

A database created by v1 is stamped at this revision instead of running it (app/db/migrate.py).

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pgn", sa.Text(), nullable=False),
        sa.Column("user_color", sa.String(5), nullable=False),
        sa.Column("elo", sa.Integer(), nullable=False),
        sa.Column("playstyle", sa.Text(), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "engine_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=True),
        sa.Column("fen", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(6), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("game_id", "fen", "tier"),
    )
    op.create_index("ix_engine_results_game_id", "engine_results", ["game_id"])
    op.create_table(
        "game_summaries",
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_chat_messages_game_id", "chat_messages", ["game_id"])
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=True),
        sa.Column("endpoint", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_llm_usage_game_id", "llm_usage", ["game_id"])
    op.create_table(
        "pending_tool_calls",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("tool_use", sa.JSON(), nullable=False),
        sa.Column("positions", sa.JSON(), nullable=False),
        sa.Column("extra_results", sa.JSON(), nullable=False),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_pending_tool_calls_game_id", "pending_tool_calls", ["game_id"])


def downgrade() -> None:
    for table in (
        "pending_tool_calls",
        "llm_usage",
        "chat_messages",
        "game_summaries",
        "engine_results",
        "games",
    ):
        op.drop_table(table)
