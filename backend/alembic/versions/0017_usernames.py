"""The player's Chess.com and Lichess usernames, for detecting their color in a PGN.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(sa.Column("chesscom_username", sa.String(50)))
        batch.add_column(sa.Column("lichess_username", sa.String(50)))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("lichess_username")
        batch.drop_column("chesscom_username")
