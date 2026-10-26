"""User scoping (SPEC_V2 §4.2, §12): games, engine results, and usage belong to a user.

Existing v1 games get a status from what was stored for them; `user_id` stays null until
`cli assign-games` gives them to a user.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _v1_engine_results() -> sa.Table:
    """engine_results exactly as 0001 created it, with its constraints named."""
    return sa.Table(
        "engine_results",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(36), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=True),
        sa.Column("fen", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(6), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name="fk_engine_results_game_id_games"),
        sa.UniqueConstraint("game_id", "fen", "tier", name="uq_engine_results_game_id_fen_tier"),
        sa.Index("ix_engine_results_game_id", "game_id"),
    )


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("time_control_category", sa.String(10), nullable=True))
        batch.add_column(sa.Column("user_result", sa.String(4), nullable=True))
        batch.add_column(sa.Column("played_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(10), nullable=False, server_default="uploaded")
        )
        batch.add_column(
            sa.Column("source", sa.String(10), nullable=False, server_default="single")
        )
        batch.create_foreign_key("fk_games_user_id_users", "users", ["user_id"], ["id"])
        batch.create_index("ix_games_user_id_played_at", ["user_id", "played_at"])

    # Rebuilt from an explicit definition, not reflection: v1 created the unique constraint
    # without a name, and SQLite's table rebuild silently drops unnamed constraints.
    with op.batch_alter_table("engine_results", copy_from=_v1_engine_results()) as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_engine_results_user_id_users", "users", ["user_id"], ["id"])

    with op.batch_alter_table("llm_usage") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("task", sa.String(20), nullable=True))
        batch.create_foreign_key("fk_llm_usage_user_id_users", "users", ["user_id"], ["id"])
        batch.create_index("ix_llm_usage_user_id", ["user_id"])

    # v1 games: a stored summary means the analysis finished; scan results mean it started.
    op.execute(
        "UPDATE games SET status = 'analyzed' WHERE id IN (SELECT game_id FROM game_summaries)"
    )
    op.execute(
        "UPDATE games SET status = 'scanned' WHERE status = 'uploaded' "
        "AND id IN (SELECT game_id FROM engine_results WHERE tier = 'scan')"
    )
    op.execute("UPDATE llm_usage SET task = endpoint WHERE task IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("llm_usage") as batch:
        batch.drop_index("ix_llm_usage_user_id")
        batch.drop_constraint("fk_llm_usage_user_id_users", type_="foreignkey")
        batch.drop_column("task")
        batch.drop_column("user_id")
    with op.batch_alter_table("engine_results") as batch:
        batch.drop_constraint("fk_engine_results_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
    with op.batch_alter_table("games") as batch:
        batch.drop_index("ix_games_user_id_played_at")
        batch.drop_constraint("fk_games_user_id_users", type_="foreignkey")
        for column in (
            "source",
            "status",
            "played_at",
            "user_result",
            "time_control_category",
            "user_id",
        ):
            batch.drop_column(column)
