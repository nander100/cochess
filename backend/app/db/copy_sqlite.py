"""Copy the v3 SQLite database into an empty Postgres database and check the copy (SPEC_V4 §12.1).

v3 ran SQLite without foreign keys and SQLite never enforces `String(n)` lengths, while Postgres
enforces both. So `find_problems` lists rows pointing at missing rows and text longer than its
column, and `copy_database` refuses to copy until there are none (PLAN_V4 adjustment 5). Rows are
read and written through the app's own table definitions, so timestamps and JSON convert the same
way the app reads them. Each table is then compared by row count and a checksum.
"""

import hashlib
import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, Engine, String, Table, func, insert, inspect, select, text

from app.db.migrate import alembic_config, upgrade
from app.db.models import Base

_BATCH = 500


class CopyError(Exception):
    pass


class Problem(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["missing_parent", "too_long"]
    table: str
    column: str
    rows: int
    detail: str


class TableCopy(BaseModel):
    model_config = ConfigDict(frozen=True)

    table: str
    source_rows: int
    target_rows: int
    source_checksum: str
    target_checksum: str

    @property
    def matches(self) -> bool:
        return (self.source_rows, self.source_checksum) == (self.target_rows, self.target_checksum)


def find_problems(source: Engine) -> list[Problem]:
    """Rows that Postgres would refuse: missing parents and text too long for its column."""
    _require_latest_schema(source)
    with source.connect() as connection:
        tables = Base.metadata.sorted_tables
        return [problem for table in tables for problem in _table_problems(connection, table)]


def copy_database(source: Engine, target: Engine) -> list[TableCopy]:
    """Copy every table from `source` into the empty `target`, then compare each table."""
    problems = find_problems(source)
    if problems:
        raise CopyError(f"{len(problems)} problems found; run with --check-only to list them")
    _require_empty(target)
    upgrade(target)
    with source.connect() as reader, target.begin() as writer:
        for table in Base.metadata.sorted_tables:
            for batch in _batches(reader, table):
                writer.execute(insert(table), batch)
        if writer.dialect.name == "postgresql":
            _reset_sequences(writer)
    with source.connect() as before, target.connect() as after:
        return [_compare(table, before, after) for table in Base.metadata.sorted_tables]


def describe(problems: Sequence[Problem]) -> str:
    """The problem list as the CLI prints it."""
    if not problems:
        return f"No problems found in {len(Base.metadata.tables)} tables."
    lines = [f"{len(problems)} problems to fix before copying:"]
    lines += [f"  {p.table}.{p.column}: {p.detail} ({p.kind})" for p in problems]
    return "\n".join(lines)


def _table_problems(connection: Connection, table: Table) -> Iterator[Problem]:
    for key in table.foreign_keys:
        column, parent = key.parent, key.column
        missing = ~select(parent).where(parent == column).exists()
        query = select(func.count()).select_from(table).where(column.is_not(None), missing)
        if rows := int(connection.execute(query).scalar_one()):
            yield Problem(
                kind="missing_parent",
                table=table.name,
                column=column.name,
                rows=rows,
                detail=f"{rows} rows point at {parent.table.name} rows that don't exist",
            )
    for column in table.columns:
        length = getattr(column.type, "length", None)
        if not isinstance(column.type, String) or length is None:
            continue
        query = select(func.count()).select_from(table).where(func.length(column) > length)
        if rows := int(connection.execute(query).scalar_one()):
            yield Problem(
                kind="too_long",
                table=table.name,
                column=column.name,
                rows=rows,
                detail=f"{rows} values are longer than {length} characters",
            )


def _require_latest_schema(engine: Engine) -> None:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise CopyError(
            f"the source database is at revision {current}, not the latest schema ({head}). "
            "Start the app on it once (it migrates at startup), then copy."
        )


def _require_empty(target: Engine) -> None:
    with target.connect() as connection:
        existing = set(inspect(connection).get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name in existing and _count(connection, table):
                raise CopyError(f"the target database is not empty ({table.name} has rows)")


def _batches(connection: Connection, table: Table) -> Iterator[list[dict[str, Any]]]:
    result = connection.execute(select(table).order_by(*table.primary_key.columns))
    while rows := result.fetchmany(_BATCH):
        yield [dict(row._mapping) for row in rows]


def _reset_sequences(connection: Connection) -> None:
    """Copied rows kept their ids, so each id sequence must continue after the highest one."""
    for table in Base.metadata.sorted_tables:
        column = table.autoincrement_column
        if column is None:
            continue
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table, :column), "
                f'COALESCE(MAX("{column.name}"), 1), MAX("{column.name}") IS NOT NULL) '
                f'FROM "{table.name}"'
            ),
            {"table": table.name, "column": column.name},
        )


def _compare(table: Table, source: Connection, target: Connection) -> TableCopy:
    return TableCopy(
        table=table.name,
        source_rows=_count(source, table),
        target_rows=_count(target, table),
        source_checksum=_checksum(source, table),
        target_checksum=_checksum(target, table),
    )


def _count(connection: Connection, table: Table) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def _checksum(connection: Connection, table: Table) -> str:
    digest = hashlib.sha256()
    for batch in _batches(connection, table):
        for row in batch:
            values = [_normal(row[column.name]) for column in table.columns]
            digest.update(json.dumps(values, sort_keys=True, default=str).encode())
    return digest.hexdigest()


def _normal(value: object) -> object:
    """One spelling per value on both databases: UTC timestamps, JSON with sorted keys."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    return value
