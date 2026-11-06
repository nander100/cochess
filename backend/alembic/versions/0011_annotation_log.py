"""Dropped coach annotations (SPEC_V3 §6, §11.2).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "annotation_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id")),
        sa.Column("task", sa.String(20), nullable=False),
        sa.Column("moment_index", sa.Integer()),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("shape", sa.String(32)),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_annotation_log_user_id", "annotation_log", ["user_id"])
    op.create_index("ix_annotation_log_game_id", "annotation_log", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_annotation_log_game_id", table_name="annotation_log")
    op.drop_index("ix_annotation_log_user_id", table_name="annotation_log")
    op.drop_table("annotation_log")
