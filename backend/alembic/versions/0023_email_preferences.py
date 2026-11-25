"""Accounts and legal (SPEC_V4 §11, §12.4): the emails a player turned off, and an outbox address
for the one email sent after an account is deleted (wiped once sent).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_preferences",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_email_preferences_user_id_users"
        ),
        sa.PrimaryKeyConstraint("user_id", "kind", name="pk_email_preferences"),
    )
    with op.batch_alter_table("email_outbox") as batch:
        batch.add_column(sa.Column("to_address", sa.String(320), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("email_outbox") as batch:
        batch.drop_column("to_address")
    op.drop_table("email_preferences")
