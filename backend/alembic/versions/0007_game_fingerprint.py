"""Game fingerprints, so a player can't upload the same game twice.

Not unique in the schema: databases from before this revision can already hold duplicates.
The upload route checks it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("fingerprint", sa.String(64), nullable=True))
        batch.create_index("ix_games_user_id_fingerprint", ["user_id", "fingerprint"])


def downgrade() -> None:
    with op.batch_alter_table("games") as batch:
        batch.drop_index("ix_games_user_id_fingerprint")
        batch.drop_column("fingerprint")
