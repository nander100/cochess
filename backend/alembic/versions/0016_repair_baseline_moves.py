"""Repair: add baseline_reports.moves where an early 0014 left it out.

A development database migrated while 0014 was still being written recorded 0014 without the
baseline report's move-tag column, so the dashboard and baseline report failed on it. Applied
migrations are never edited; this one adds the column only where it's missing.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_moves() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("baseline_reports")
    return any(column["name"] == "moves" for column in columns)


def upgrade() -> None:
    if not _has_moves():
        with op.batch_alter_table("baseline_reports") as batch:
            batch.add_column(sa.Column("moves", sa.JSON()))


def downgrade() -> None:
    # 0014 owns the column; there is nothing of this repair's own to undo.
    pass
