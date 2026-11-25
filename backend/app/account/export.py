"""A player's data export (SPEC_V4 §11): one zip with their profile, settings, every game as an
annotated PGN (variations, labels, moment notes, evaluations), their coaching conversations as the
player saw them, baseline reports and credit history. Only rows scoped to the player are read."""

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.variations import annotated_pgn
from app.config import Settings
from app.db.models import (
    BaselineReportRow,
    ChatMessageRow,
    CreditLedgerRow,
    Game,
    MomentProgressRow,
    TermsAcceptance,
    User,
    UserSettingsRow,
)

# Coach text keeps placeholders for the app to fill in: "[rook takes on d7](cc:move/0)". The
# label is what the player read; board tags have no words of their own.
_PLACEHOLDER = re.compile(r"\[([^\]]*)\]\(cc:(move|line|board)/\d+\)")
_SETTINGS = (
    "theme", "board_scheme", "piece_set", "sounds", "engine_panel", "coach_detail_level",
    "playback_seconds", "chesscom_username", "lichess_username", "coach_strength",
)  # fmt: skip

README = """Your CoChess data, exported {when} (UTC).

profile.json   your account: name, email, rating, how you play, status, terms you accepted
settings.json  your app settings and your Chess.com and Lichess usernames
games/         every game as a PGN file, with the engine's labels and evaluations, critical-moment
               notes and your saved variations (any chess app can open these)
coaching/      the coach's synopsis, your chats and critical-moment conversations, per game
reports/       your baseline reports
credits.csv    every change to your coaching credits
"""


def build_export(session: Session, user: User, settings: Settings, now: datetime) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", README.format(when=f"{now:%Y-%m-%d %H:%M}"))
        archive.writestr("profile.json", _json(_profile(session, user)))
        archive.writestr("settings.json", _json(_settings(session, user)))
        games = session.scalars(
            select(Game).where(Game.user_id == user.id).order_by(Game.created_at, Game.id)
        ).all()
        for number, game in enumerate(games, start=1):
            text, filename = annotated_pgn(session, game, settings)
            stem = f"{number:03}-{filename.removesuffix('.pgn')}"
            archive.writestr(f"games/{stem}.pgn", text)
            coaching = _coaching(session, user, game)
            if coaching:
                archive.writestr(f"coaching/{stem}.md", coaching)
        reports = session.scalars(
            select(BaselineReportRow).where(BaselineReportRow.user_id == user.id)
        )
        for report in reports:
            archive.writestr(f"reports/baseline-{report.created_at:%Y-%m-%d}.md", report.text)
        archive.writestr("credits.csv", _credits(session, user, settings))
    return buffer.getvalue()


def shown(text: str) -> str:
    """Coach text as the player read it: placeholders replaced by their words."""
    return _PLACEHOLDER.sub(lambda m: m[1] if m[2] != "board" else "", text).replace("  ", " ")


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n"


def _profile(session: Session, user: User) -> dict[str, Any]:
    terms = session.scalars(select(TermsAcceptance).where(TermsAcceptance.user_id == user.id))
    return {
        "name": user.name, "email": user.email, "elo": user.elo,
        "time_control": user.time_control, "playstyle": user.playstyle,
        "status": user.status, "age_band": user.age_band,
        "google_connected": user.google_sub is not None, "joined": user.created_at,
        "subscription_status": user.subscription_status,
        "terms_accepted": [{"version": t.version, "at": t.accepted_at} for t in terms],
    }  # fmt: skip


def _settings(session: Session, user: User) -> dict[str, Any]:
    row = session.get(UserSettingsRow, user.id)
    return {field: getattr(row, field) for field in _SETTINGS} if row else {}


def _coaching(session: Session, user: User, game: Game) -> str:
    """The game's coaching as markdown: the synopsis, the chat, then each critical moment."""
    parts: list[str] = []
    rows = session.scalars(
        select(ChatMessageRow).where(ChatMessageRow.game_id == game.id).order_by(ChatMessageRow.id)
    )
    for row in rows:
        content = row.content
        if content.get("type") == "synopsis":
            parts.append(f"## Synopsis\n\n{shown(str(content.get('text', '')))}")
        elif "display" in content:
            who = "You" if row.role == "user" else "Coach"
            where = f" ({content['where']})" if content.get("where") else ""
            parts.append(f"**{who}{where}:** {shown(str(content['display']))}")
    moments = session.scalars(
        select(MomentProgressRow)
        .where(MomentProgressRow.game_id == game.id, MomentProgressRow.user_id == user.id)
        .order_by(MomentProgressRow.moment_index)
    )
    for moment in moments:
        parts.append(f"## Critical moment {moment.moment_index}")
        parts.extend(_moment_lines(moment.messages))
    return "\n\n".join(parts) + "\n" if parts else ""


def _moment_lines(messages: Iterable[dict[str, Any]]) -> list[str]:
    lines = []
    for message in messages:
        text = message.get("display") or message.get("text")
        if text:
            who = "You" if message.get("role") == "player" else "Coach"
            lines.append(f"**{who}:** {shown(str(text))}")
    return lines


def _credits(session: Session, user: User, settings: Settings) -> str:
    per_credit = settings.credits.microusd_per_credit
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "kind", "credits", "note", "expires"])
    entries = session.scalars(
        select(CreditLedgerRow)
        .where(CreditLedgerRow.user_id == user.id)
        .order_by(CreditLedgerRow.created_at, CreditLedgerRow.id)
    )
    for entry in entries:
        expires = entry.expires_at.isoformat() if entry.expires_at else ""
        credits = f"{entry.delta_microusd / per_credit:g}"
        writer.writerow(
            [entry.created_at.isoformat(), entry.kind, credits, entry.note or "", expires]
        )
    return out.getvalue()
