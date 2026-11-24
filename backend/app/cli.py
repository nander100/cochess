"""Owner commands (SPEC_V2 §4.1, §4.4). Run from backend/: `uv run python -m app.cli --help`.

create-user --name "Alex"     add a player
invite --user Alex            print a one-time login link (valid 7 days)
assign-games --user Alex      give every game without an owner (v1 games) to a player
admit --user NAME_OR_EMAIL      accept a player from the waitlist (sends the acceptance email)
suspend --user X --reason TEXT  pause a player's access (signs them out everywhere)
restore --user X              give a paused player their access back
set-role --user X --role owner|player
migrate-sqlite --from URL --to URL [--check-only]
                              copy the v3 SQLite database into an empty Postgres database
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO

from sqlalchemy.orm import Session, sessionmaker

from app.auth.accounts import AccountError, admit, restore, set_role, suspend
from app.auth.service import UserExistsError, create_invite, create_user, find_account, find_user
from app.config import Settings, get_settings
from app.db.copy_sqlite import CopyError, copy_database, describe, find_problems
from app.db.games import assign_unowned_games, fill_fingerprints, rebuild_summaries
from app.db.migrate import upgrade
from app.db.models import User
from app.db.session import make_engine


class CliError(Exception):
    pass


def main(
    argv: Sequence[str] | None = None, settings: Settings | None = None, out: TextIO = sys.stdout
) -> int:
    args = _parser().parse_args(argv)
    if args.command == "migrate-sqlite":
        return _migrate_sqlite(args, out)
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    upgrade(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        try:
            message = _run(args, session, settings)
        except CliError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    print(message, file=out)
    return 0


def _run(args: argparse.Namespace, session: Session, settings: Settings) -> str:
    if args.command == "create-user":
        try:
            user = create_user(session, args.name)
        except UserExistsError as error:
            raise CliError(f'a user named "{args.name.strip()}" already exists') from error
        except ValueError as error:
            raise CliError(str(error)) from error
        return f'Created user "{user.name}". Next: invite --user "{user.name}"'
    if args.command == "invite":
        user = _user(session, args.user)
        token = create_invite(session, user, datetime.now(UTC), settings.auth)
        base = (args.base_url or settings.public_base_url).rstrip("/")
        days = settings.auth.invite_ttl_days
        # The token is in the fragment, so it never reaches server logs or Referer headers.
        link = f"{base}/redeem#token={token}"
        return f"Login link for {user.name} (works once, for {days} days):\n{link}"
    if args.command == "backfill":
        player = _user(session, args.user) if args.user else None
        rebuilt = rebuild_summaries(session, settings, player)
        lines = [f"Rebuilt {rebuilt} game summar{'y' if rebuilt == 1 else 'ies'}."]
        for games in fill_fingerprints(session, settings):
            if player is None or games[0].user_id == player.id:
                ids = ", ".join(f"{g.id} ({g.user_color})" for g in games)
                lines.append(f"Duplicate uploads of one game: {ids}")
        return "\n".join(lines)
    if args.command in ("admit", "suspend", "restore", "set-role"):
        return _account_action(args, session)
    user = _user(session, args.user)
    count = assign_unowned_games(session, user)
    return f"Assigned {count} game(s) to {user.name}."


def _account_action(args: argparse.Namespace, session: Session) -> str:
    user = find_account(session, args.user)
    if user is None:
        raise CliError(f'no player named or with the email "{args.user}"')
    now = datetime.now(UTC)
    try:
        if args.command == "admit":
            admit(session, user, now)
            message = f'Accepted "{user.name}": they can sign in now (acceptance email queued).'
        elif args.command == "suspend":
            suspend(session, user, now, reason=args.reason, tell_reason=args.tell_reason)
            message = f'Paused "{user.name}": signed out everywhere (email queued).'
        elif args.command == "restore":
            restore(session, user, now)
            message = f'Restored "{user.name}" (status: {user.status}).'
        else:
            set_role(user, args.role)
            message = f'"{user.name}" is now {args.role}.'
    except AccountError as error:
        raise CliError(str(error)) from error
    session.commit()
    return message


def _migrate_sqlite(args: argparse.Namespace, out: TextIO) -> int:
    """Check, then copy (SPEC_V4 §12.1). Works on the two databases named, not DATABASE_URL."""
    if not args.source.startswith("sqlite:///"):
        print(
            "error: --from must be a SQLite file URL (sqlite:///path/to/cochess.db)",
            file=sys.stderr,
        )
        return 1
    if not args.check_only and not args.target:
        print("error: --to is needed unless --check-only", file=sys.stderr)
        return 1
    source = make_engine(args.source)
    try:
        problems = find_problems(source)
        if args.check_only or problems:
            print(describe(problems), file=out)
            return 1 if problems else 0
        results = copy_database(source, make_engine(args.target))
    except CopyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for result in results:
        status = "ok" if result.matches else "DIFFERENT"
        print(
            f"  {result.table}: {result.source_rows} -> {result.target_rows} rows, {status}",
            file=out,
        )
    rows = sum(r.target_rows for r in results)
    if all(r.matches for r in results):
        print(f"Copied {rows} rows in {len(results)} tables; every table matches.", file=out)
        return 0
    print("The copy doesn't match the source: don't switch DATABASE_URL to it.", file=out)
    return 1


def _user(session: Session, name: str) -> User:
    user = find_user(session, name)
    if user is None:
        raise CliError(f'no user named "{name}" (create-user first)')
    return user


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="CoChess owner commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-user", help="add a player").add_argument("--name", required=True)
    invite = commands.add_parser("invite", help="print a one-time login link")
    invite.add_argument("--user", required=True)
    invite.add_argument("--base-url", help="where players open CoChess (default PUBLIC_BASE_URL)")
    assign = commands.add_parser("assign-games", help="give v1 games without an owner to a player")
    assign.add_argument("--user", required=True)
    backfill = commands.add_parser(
        "backfill", help="rebuild analyzed games' summaries from stored engine results"
    )
    backfill.add_argument("--user", help="only this player's games (default: everyone's)")
    for name, text in (
        ("admit", "accept a player from the waitlist"),
        ("suspend", "pause a player's access"),
        ("restore", "give a paused player their access back"),
        ("set-role", "make a player the owner, or a player again"),
    ):
        action = commands.add_parser(name, help=text)
        action.add_argument("--user", required=True, help="the player's name or email")
        if name == "suspend":
            action.add_argument("--reason", required=True, help="kept with the owner")
            action.add_argument(
                "--tell-reason", action="store_true", help="also put the reason in the email"
            )
        if name == "set-role":
            action.add_argument("--role", required=True, choices=["owner", "player"])
    copy = commands.add_parser(
        "migrate-sqlite", help="copy the v3 SQLite database into an empty Postgres database"
    )
    copy.add_argument("--from", dest="source", required=True, help="sqlite:///path/to/cochess.db")
    copy.add_argument("--to", dest="target", help="postgresql+psycopg://... (empty database)")
    copy.add_argument(
        "--check-only", action="store_true", help="list problems without copying anything"
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
