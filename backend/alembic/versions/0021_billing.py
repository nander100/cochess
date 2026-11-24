"""Payments through Stripe Managed Payments (SPEC_V4 §6.3).

Players gain the payment provider's customer id and their subscription's status and period end;
every webhook event is stored once in `billing_events`.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("billing_provider", sa.String(10)))
        batch.add_column(sa.Column("billing_customer_id", sa.String(64)))
        batch.add_column(sa.Column("subscription_status", sa.String(20)))
        batch.add_column(sa.Column("subscription_period_end", _TIME))
        batch.create_unique_constraint("uq_users_billing_customer_id", ["billing_customer_id"])

    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("event_id", sa.String(80), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("received_at", _TIME, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_billing_events_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_events"),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_events_provider_event_id"),
    )
    op.create_index("ix_billing_events_user_id", "billing_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_events_user_id", table_name="billing_events")
    op.drop_table("billing_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_billing_customer_id", type_="unique")
        batch.drop_column("subscription_period_end")
        batch.drop_column("subscription_status")
        batch.drop_column("billing_customer_id")
        batch.drop_column("billing_provider")
