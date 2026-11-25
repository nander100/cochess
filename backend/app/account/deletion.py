"""Deleting an account (SPEC_V4 §11): in the caller's transaction, everything that points at the
player or their games is deleted, except money and audit records, which lose the player's id and
stay (llm_usage, credit_ledger, billing_events, admin_actions).

The tables come from the models' own foreign keys, children first, so a table added later is
covered without touching this file; tests/account/test_deletion.py then checks that no text or
JSON column anywhere still holds the player's id.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, ColumnElement, Table, delete, false, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import Base, CreditLedgerRow, Game, PendingSignup, User
from app.email.outbox import queue_farewell

# Financial and audit records: kept, with the player (and their games) cut out.
ANONYMIZED = frozenset({"llm_usage", "credit_ledger", "billing_events", "admin_actions"})


def delete_account(session: Session, user: User, now: datetime) -> None:
    """Delete `user` and what's theirs (not committed here). Queues the goodbye email to the
    address on file first: it's the one place the address outlives the account."""
    if user.email:
        queue_farewell(session, user.email, user.name, now)
    games = list(session.scalars(select(Game.id).where(Game.user_id == user.id)))
    for table in reversed(Base.metadata.sorted_tables):
        if table.name != "users":
            _clear(session, table, user.id, games)
    # Ledger sources can name the player ("trial:<id>"): keep them unique, without the id.
    placeholder = f"deleted-{uuid.uuid4().hex[:12]}"
    session.execute(
        update(CreditLedgerRow)
        .where(CreditLedgerRow.source.contains(user.id))
        .values(source=func.replace(CreditLedgerRow.source, user.id, placeholder))
    )
    if user.google_sub:
        session.execute(delete(PendingSignup).where(PendingSignup.google_sub == user.google_sub))
    session.delete(user)
    session.flush()


def _clear(session: Session, table: Table, user_id: str, games: list[str]) -> None:
    references = [
        (column, fk.column.table.name)
        for column in table.columns
        for fk in column.foreign_keys
        if fk.column.table.name in ("users", "games")
    ]
    if not references:
        return
    if table.name in ANONYMIZED:
        for column, target in references:
            match = _match(column, target, user_id, games)
            session.execute(update(table).where(match).values({column.name: None}))
        return
    if table.name == "email_outbox":  # the goodbye email has no user id: only theirs go
        references = [(c, t) for c, t in references if t == "users"]
    matches = [_match(column, target, user_id, games) for column, target in references]
    session.execute(delete(table).where(or_(*matches)))


def _match(column: Column[Any], target: str, user_id: str, games: list[str]) -> ColumnElement[bool]:
    if target == "users":
        return column == user_id
    return column.in_(games) if games else false()
