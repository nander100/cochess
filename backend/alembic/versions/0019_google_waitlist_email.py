"""Google sign-in, the waitlist and account email (SPEC_V4 §4, §12.4).

Users gain Google's account id and verified email, a status (players already here stay active),
a role, the banded age check, waitlist dates and when they were last active. New tables: OAuth
round trips, pending sign-ups, terms acceptances, and the email outbox.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(320)))
        batch.add_column(sa.Column("google_sub", sa.String(255)))
        batch.add_column(
            sa.Column("status", sa.String(12), nullable=False, server_default="active")
        )
        batch.add_column(sa.Column("role", sa.String(10), nullable=False, server_default="player"))
        batch.add_column(sa.Column("age_band", sa.String(8)))
        batch.add_column(sa.Column("age_checked_at", _TIME))
        batch.add_column(sa.Column("waitlisted_at", _TIME))
        batch.add_column(sa.Column("admitted_at", _TIME))
        batch.add_column(sa.Column("last_active_at", _TIME))
        batch.create_unique_constraint("uq_users_google_sub", ["google_sub"])

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("intent", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("expires_at", _TIME, nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_oauth_states_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_states"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])

    op.create_table(
        "pending_signups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("expires_at", _TIME, nullable=False),
        sa.Column("created_at", _TIME, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pending_signups"),
        sa.UniqueConstraint("token_hash", name="uq_pending_signups_token_hash"),
    )

    op.create_table(
        "terms_acceptances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("accepted_at", _TIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_terms_acceptances_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_terms_acceptances"),
    )
    op.create_index("ix_terms_acceptances_user_id", "terms_acceptances", ["user_id"])

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", _TIME, nullable=False),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("created_at", _TIME, nullable=False),
        sa.Column("sent_at", _TIME, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_email_outbox_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_email_outbox"),
        sa.UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
    )
    op.create_index("ix_email_outbox_user_id", "email_outbox", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_user_id", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("ix_terms_acceptances_user_id", table_name="terms_acceptances")
    op.drop_table("terms_acceptances")
    op.drop_table("pending_signups")
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_google_sub", type_="unique")
        for column in (
            "last_active_at",
            "admitted_at",
            "waitlisted_at",
            "age_checked_at",
            "age_band",
            "role",
            "status",
            "google_sub",
            "email",
        ):
            batch.drop_column(column)
