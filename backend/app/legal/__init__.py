"""Terms and privacy (SPEC_V4 §11): the texts, served from files the owner can replace without a
rebuild (LEGAL__TEXTS_DIR), and the consent records for the current terms version."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import LegalSettings
from app.db.models import TermsAcceptance, User

LegalKind = Literal["terms", "privacy"]
_PACKAGED = Path(__file__).parent / "texts"


def legal_text(settings: LegalSettings, kind: LegalKind) -> str:
    folder = Path(settings.texts_dir) if settings.texts_dir else _PACKAGED
    return (folder / f"{kind}.md").read_text(encoding="utf-8")


def has_accepted(session: Session, user: User, version: str) -> bool:
    query = select(TermsAcceptance.id).where(
        TermsAcceptance.user_id == user.id, TermsAcceptance.version == version
    )
    return session.scalar(query.limit(1)) is not None


def accept_terms(session: Session, user: User, version: str, now: datetime) -> None:
    """Record acceptance of `version` once (in the caller's transaction)."""
    if not has_accepted(session, user, version):
        session.add(TermsAcceptance(user_id=user.id, version=version, accepted_at=now))
