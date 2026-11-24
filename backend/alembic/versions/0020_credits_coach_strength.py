"""Coaching credits and coach strength (SPEC_V4 §5, §7).

Each coach call gets its cost and tier; players get an unmetered flag (owner and test accounts)
and a coach strength; walkthroughs are cached per tier. New tables: the credit ledger and the
balance kept with it.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("unmetered", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("llm_usage") as batch:
        batch.add_column(sa.Column("cost_microusd", sa.BigInteger()))
        batch.add_column(sa.Column("tier", sa.String(10)))
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(sa.Column("coach_strength", sa.String(8)))
    with op.batch_alter_table("walkthroughs") as batch:
        batch.add_column(
            sa.Column("tier", sa.String(10), nullable=False, server_default="standard")
        )
        batch.drop_constraint("uq_walkthroughs_user_line", type_="unique")
        batch.create_unique_constraint(
            "uq_walkthroughs_user_line_tier", ["user_id", "start_fen", "line_key", "tier"]
        )

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("delta_microusd", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("bucket", sa.String(10), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("expires_at", _TIME, nullable=True),
        sa.Column("created_at", _TIME, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_credit_ledger_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_credit_ledger"),
        sa.UniqueConstraint("kind", "source", name="uq_credit_ledger_kind_source"),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])

    op.create_table(
        "credit_balances",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("allowance_microusd", sa.BigInteger(), nullable=False),
        sa.Column("lasting_microusd", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", _TIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_credit_balances_user_id_users"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_credit_balances"),
    )


def downgrade() -> None:
    op.drop_table("credit_balances")
    op.drop_index("ix_credit_ledger_user_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    with op.batch_alter_table("walkthroughs") as batch:
        batch.drop_constraint("uq_walkthroughs_user_line_tier", type_="unique")
        batch.create_unique_constraint(
            "uq_walkthroughs_user_line", ["user_id", "start_fen", "line_key"]
        )
        batch.drop_column("tier")
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("coach_strength")
    with op.batch_alter_table("llm_usage") as batch:
        batch.drop_column("tier")
        batch.drop_column("cost_microusd")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("unmetered")
