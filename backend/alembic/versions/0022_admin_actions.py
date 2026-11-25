"""The owner dashboard (SPEC_V4 §10): the audit log of owner actions, indexes on the timestamps
its overview filters by, and the payment each billing event is about (refunds report a running
total per payment, so revenue needs it).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.String(36), nullable=True),
        sa.Column("target_user_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["users.id"], name="fk_admin_actions_admin_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["users.id"], name="fk_admin_actions_target_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_actions"),
    )
    with op.batch_alter_table("billing_events") as batch:
        batch.add_column(sa.Column("object_id", sa.String(80), nullable=True))
    op.create_index("ix_admin_actions_target_user_id", "admin_actions", ["target_user_id"])
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])
    op.create_index("ix_credit_ledger_kind_created_at", "credit_ledger", ["kind", "created_at"])
    op.create_index("ix_billing_events_received_at", "billing_events", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_billing_events_received_at", table_name="billing_events")
    op.drop_index("ix_credit_ledger_kind_created_at", table_name="credit_ledger")
    op.drop_index("ix_llm_usage_created_at", table_name="llm_usage")
    op.drop_index("ix_admin_actions_target_user_id", table_name="admin_actions")
    op.drop_table("admin_actions")
    with op.batch_alter_table("billing_events") as batch:
        batch.drop_column("object_id")
