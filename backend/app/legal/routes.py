"""The legal pages (public) and accepting the current terms (any signed-in account, including a
waitlisted or paused one: a new version asks everyone before they continue). SPEC_V4 §11."""

from datetime import UTC, datetime
from typing import Annotated, cast, get_args

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session
from app.auth.deps import CurrentAccount
from app.config import Settings
from app.legal import LegalKind, accept_terms, legal_text

router = APIRouter(tags=["legal"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

KINDS = get_args(LegalKind)
OUTDATED = "These terms have been updated. Reload the page to read the current version."


class LegalPage(BaseModel):
    kind: LegalKind
    version: str
    markdown: str


class AcceptTerms(BaseModel):
    version: str = Field(min_length=1, max_length=40)


@router.get("/api/legal/{kind}")
def read_legal(kind: str, settings: SettingsDep) -> LegalPage:
    if kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such page.")
    page = cast(LegalKind, kind)
    return LegalPage(
        kind=page, version=settings.legal.terms_version, markdown=legal_text(settings.legal, page)
    )


@router.post("/api/me/terms", status_code=status.HTTP_204_NO_CONTENT)
def accept(
    body: AcceptTerms, user: CurrentAccount, session: SessionDep, settings: SettingsDep
) -> None:
    """Accept the terms the page showed. An older version (the page was open across an update)
    is refused, so nobody accepts text they didn't see."""
    if body.version != settings.legal.terms_version:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=OUTDATED)
    accept_terms(session, user, body.version, datetime.now(UTC))
    session.commit()
