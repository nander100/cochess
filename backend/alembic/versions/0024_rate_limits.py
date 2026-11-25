"""Rate limits in the database (SPEC_V4 §12.2): one row per limit, who it counts and window.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name="pk_rate_limits"),
    )
    op.create_index("ix_rate_limits_window_start", "rate_limits", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_rate_limits_window_start", table_name="rate_limits")
    op.drop_table("rate_limits")
