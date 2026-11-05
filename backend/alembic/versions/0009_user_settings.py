"""Per-player settings (SPEC_V3 §4.3).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("theme", sa.String(6), nullable=False),
        sa.Column("board_scheme", sa.String(8), nullable=False),
        sa.Column("piece_set", sa.String(16), nullable=False),
        sa.Column("sounds", sa.Boolean(), nullable=False),
        sa.Column("engine_panel", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
