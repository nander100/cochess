"""Owner commands (SPEC_V2 §4.1, §4.4). Run from backend/: `uv run python -m app.cli --help`.

create-user --name "Alex"     add a player
invite --user Alex            print a one-time login link (valid 7 days)
assign-games --user Alex      give every game without an owner (v1 games) to a player
admit --user NAME_OR_EMAIL      accept a player from the waitlist (sends the acceptance email)
suspend --user X --reason TEXT  pause a player's access (signs them out everywhere)
restore --user X              give a paused player their access back
set-role --user X --role owner|player
grant-credits --user X --credits N --note TEXT   add (or, negative, remove) coaching credits
metering --user X --off|--on  never charge this player (owner, testers), or charge again
grant-trials                  give the free trial to every active player who hasn't had it
price-usage                   price coach calls recorded before v4 (no charge)
usage-report [--period 7d|30d|month|all]   the owner dashboard's overview as text
notify-terms                  email everyone who hasn't accepted the current terms version (once)
spend [--hours 24]            API cost in the last hours, in dollars (for the spend alarm)
migrate-sqlite --from URL --to URL [--check-only]
                              copy the v3 SQLite database into an empty Postgres database
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TextIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.admin import actions
from app.admin.overview import overview
from app.admin.report import usage_report
from app.auth.service import UserExistsError, create_invite, create_user, find_account, find_user
from app.billing.ledger import grant_trial
from app.billing.pricing import cost_microusd
from app.coach.client import Usage
from app.config import Settings, get_settings
from app.db.copy_sqlite import CopyError, copy_database, describe, find_problems
from app.db.games import assign_unowned_games, fill_fingerprints, rebuild_summaries
from app.db.migrate import upgrade
from app.db.models import CreditLedgerRow, EmailOutboxRow, LlmUsageRow, User
from app.db.session import make_engine
from app.email.outbox import queue_email
from app.legal import has_accepted


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
        grant_trial(session, user, datetime.now(UTC), settings.credits)  # as if accepted
        session.commit()
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
    if args.command == "spend":
        since = datetime.now(UTC) - timedelta(hours=args.hours)
        query = select(func.coalesce(func.sum(LlmUsageRow.cost_microusd), 0)).where(
            LlmUsageRow.created_at >= since
        )
        return f"{int(session.scalar(query) or 0) / 1_000_000:.4f}"
    if args.command == "notify-terms":
        return _notify_terms(session, settings)
    if args.command == "usage-report":
        return usage_report(overview(session, args.period, datetime.now(UTC)))
    if args.command in ("admit", "suspend", "restore", "set-role"):
        return _account_action(args, session, settings)
    if args.command in ("grant-credits", "metering", "grant-trials", "price-usage"):
        return _credit_action(args, session, settings)
    user = _user(session, args.user)
    count = assign_unowned_games(session, user)
    return f"Assigned {count} game(s) to {user.name}."


def _account_action(args: argparse.Namespace, session: Session, settings: Settings) -> str:
    user = find_account(session, args.user)
    if user is None:
        raise CliError(f'no player named or with the email "{args.user}"')
    now = datetime.now(UTC)
    try:
        if args.command == "admit":
            actions.accept(session, None, user, now, settings.credits)
            message = f'Accepted "{user.name}": they can sign in now (acceptance email queued).'
        elif args.command == "suspend":
            actions.suspend(
                session, None, user, now, reason=args.reason, tell_reason=args.tell_reason
            )
            message = f'Paused "{user.name}": signed out everywhere (email queued).'
        elif args.command == "restore":
            actions.restore(session, None, user, now)
            message = f'Restored "{user.name}" (status: {user.status}).'
        else:
            actions.set_role(session, None, user, args.role, now)
            message = f'"{user.name}" is now {args.role}.'
    except actions.ActionError as error:
        raise CliError(str(error)) from error
    session.commit()
    return message


def _notify_terms(session: Session, settings: Settings) -> str:
    """After LEGAL__TERMS_VERSION changes (SPEC_V4 §12.4 terms_updated): one email per account
    with an address that hasn't accepted this version. Safe to run again: each is sent once."""
    version, now = settings.legal.terms_version, datetime.now(UTC)
    accounts = session.scalars(
        select(User).where(User.status != "deleted", User.email.is_not(None))
    ).all()
    queued = 0
    for user in accounts:
        key = f"terms_updated:{version}:{user.id}"
        if has_accepted(session, user, version) or _queued(session, key):
            continue
        queue_email(session, user, "terms_updated", key, now=now)
        queued += 1
    session.commit()
    return f"Queued {queued} terms_updated email(s) for version {version}."


def _queued(session: Session, key: str) -> bool:
    return (
        session.scalar(select(EmailOutboxRow.id).where(EmailOutboxRow.dedupe_key == key))
        is not None
    )


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


def _credit_action(args: argparse.Namespace, session: Session, settings: Settings) -> str:
    """Owner credit commands (SPEC_V4 §5), audited like the dashboard's (§10.3)."""
    now = datetime.now(UTC)
    if args.command == "grant-trials":
        players = session.scalars(select(User).where(User.status == "active")).all()
        had = set(
            session.scalars(select(CreditLedgerRow.user_id).where(CreditLedgerRow.kind == "trial"))
        )
        given = [p for p in players if p.id not in had]
        for player in given:
            grant_trial(session, player, now, settings.credits)
        session.commit()
        return f"Gave the free trial to {len(given)} player(s)."
    if args.command == "price-usage":
        rows = session.scalars(select(LlmUsageRow).where(LlmUsageRow.cost_microusd.is_(None)))
        priced = 0
        for row in rows:
            usage = Usage(
                row.input_tokens, row.output_tokens, row.cache_read_tokens, row.cache_write_tokens
            )
            row.cost_microusd = cost_microusd(settings.pricing, row.model, usage)
            priced += 1
        session.commit()
        return f"Priced {priced} earlier coach call(s); nobody was charged for them."
    user = find_account(session, args.user)
    if user is None:
        raise CliError(f'no player named or with the email "{args.user}"')
    try:
        if args.command == "metering":
            actions.set_metering(session, None, user, unmetered=args.off, now=now)
            session.commit()
            state = "never charged (unmetered)" if args.off else "charged for coaching again"
            return f'"{user.name}" is now {state}.'
        actions.change_credits(
            session, None, user, args.credits, note=args.note, now=now, settings=settings.credits
        )
    except actions.ActionError as error:
        raise CliError(str(error)) from error
    session.commit()
    verb = "Added" if args.credits >= 0 else "Removed"
    return f'{verb} {abs(args.credits):g} credits for "{user.name}".'


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
    grant = commands.add_parser("grant-credits", help="add or remove coaching credits")
    grant.add_argument("--user", required=True, help="the player's name or email")
    grant.add_argument("--credits", required=True, type=float, help="negative to remove")
    grant.add_argument("--note", required=True, help="why (kept with the entry)")
    metering = commands.add_parser("metering", help="charge a player for coaching or not")
    metering.add_argument("--user", required=True, help="the player's name or email")
    switch = metering.add_mutually_exclusive_group(required=True)
    switch.add_argument("--off", action="store_true", help="never charge them")
    switch.add_argument("--on", action="store_true", help="charge them again")
    commands.add_parser("grant-trials", help="give the trial to active players without one")
    commands.add_parser("price-usage", help="price coach calls recorded before v4")
    commands.add_parser("notify-terms", help="email everyone about a new terms version")
    spend = commands.add_parser("spend", help="API cost in the last hours, in dollars")
    spend.add_argument("--hours", type=float, default=24)
    report = commands.add_parser("usage-report", help="the owner dashboard's numbers as text")
    report.add_argument("--period", choices=["7d", "30d", "month", "all"], default="30d")
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
