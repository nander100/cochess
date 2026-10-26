"""Users, invites, and sessions (SPEC_V2 §4.1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("name_key", sa.String(60), nullable=False, unique=True),
        sa.Column("elo", sa.Integer(), nullable=True),
        sa.Column("time_control", sa.String(10), nullable=True),
        sa.Column("playstyle", sa.Text(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )
    for table in ("invites", "sessions"):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            _timestamp("expires_at"),
            *([_timestamp("used_at", nullable=True)] if table == "invites" else []),
            _timestamp("created_at"),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:
    for table in ("sessions", "invites", "users"):
        op.drop_table(table)
