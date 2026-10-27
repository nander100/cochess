"""Owner commands (SPEC_V2 §4.1, §4.4). Run from backend/: `uv run python -m app.cli --help`.

create-user --name "Alex"     add a player
invite --user Alex            print a one-time login link (valid 7 days)
assign-games --user Alex      give every game without an owner (v1 games) to a player
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TextIO

from sqlalchemy.orm import Session, sessionmaker

from app.auth.service import UserExistsError, create_invite, create_user, find_user
from app.config import Settings, get_settings
from app.db.games import assign_unowned_games, rebuild_summaries
from app.db.migrate import upgrade
from app.db.models import User
from app.db.session import make_engine


class CliError(Exception):
    pass


def main(
    argv: Sequence[str] | None = None, settings: Settings | None = None, out: TextIO = sys.stdout
) -> int:
    args = _parser().parse_args(argv)
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
        return f"Rebuilt {rebuilt} game summar{'y' if rebuilt == 1 else 'ies'}."
    user = _user(session, args.user)
    count = assign_unowned_games(session, user)
    return f"Assigned {count} game(s) to {user.name}."


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
    return parser


if __name__ == "__main__":
    sys.exit(main())
