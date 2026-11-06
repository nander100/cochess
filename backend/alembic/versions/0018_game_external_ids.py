"""Imported games (SPEC_V3 §10, §11.2): the platform and its game id, unique per player.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("external_source", sa.String(10)))
        batch.add_column(sa.Column("external_id", sa.String(64)))
        batch.create_unique_constraint(
            "uq_games_user_external", ["user_id", "external_source", "external_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_constraint("uq_games_user_external", type_="unique")
        batch.drop_column("external_id")
        batch.drop_column("external_source")
