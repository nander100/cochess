"""The player's profile (SPEC_V2 §4.3): GET / PATCH /api/me."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import Profile, ProfileUpdate, TimeControl
from app.auth.deps import CurrentUser
from app.auth.service import find_user, name_key
from app.db.models import User

router = APIRouter(prefix="/api/me", tags=["profile"])


def is_complete(user: User) -> bool:
    return user.elo is not None and user.time_control is not None


def profile_of(user: User) -> Profile:
    return Profile(
        name=user.name,
        elo=user.elo,
        time_control=cast(TimeControl | None, user.time_control),  # validated on write
        playstyle=user.playstyle,
        complete=is_complete(user),
    )


@router.get("")
def read_profile(user: CurrentUser) -> Profile:
    return profile_of(user)


@router.patch("")
def update_profile(
    body: ProfileUpdate, user: CurrentUser, session: Annotated[Session, Depends(get_session)]
) -> Profile:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") is not None and name_key(changes["name"]) != user.name_key:
        if find_user(session, changes["name"]) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="That name is already taken.")
        user.name_key = name_key(changes["name"])
    for field in ("name", "elo", "time_control"):
        if changes.get(field) is not None:
            setattr(user, field, changes[field])
    if "playstyle" in changes:
        user.playstyle = changes["playstyle"] or None
    session.commit()
    return profile_of(user)
