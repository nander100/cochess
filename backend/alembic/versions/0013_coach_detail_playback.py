"""Coach detail level and playback speed settings (SPEC_V3 §9.3, §9.5).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(sa.Column("coach_detail_level", sa.String(10)))
        batch.add_column(
            sa.Column("playback_seconds", sa.Float(), nullable=False, server_default="1.5")
        )


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("playback_seconds")
        batch.drop_column("coach_detail_level")
