"""Line links in coach messages, and the baseline report's move tags (SPEC_V3 §9.4, §11.2).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "line_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("message", sa.String(20), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("start_path", sa.JSON(), nullable=False),
        sa.Column("moves", sa.JSON(), nullable=False),
        sa.Column("step_evals", sa.JSON()),
        sa.Column("settle_ply", sa.Integer()),
        sa.Column("caption", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_line_links_user_id", "line_links", ["user_id"])
    op.create_index("ix_line_links_game_id", "line_links", ["game_id"])
    with op.batch_alter_table("baseline_reports") as batch:
        batch.add_column(sa.Column("moves", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("baseline_reports") as batch:
        batch.drop_column("moves")
    op.drop_index("ix_line_links_game_id", table_name="line_links")
    op.drop_index("ix_line_links_user_id", table_name="line_links")
    op.drop_table("line_links")
