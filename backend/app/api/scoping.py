"""`OwnedGame`: the game in the URL, if it belongs to the current user; 404 otherwise.

It's a dependency, so it runs before the request body is validated: a request for someone else's
game is "not found" whatever it sends (SPEC_V2 §4.2).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.auth.deps import CurrentUser
from app.db.games import GameNotFoundError, get_game
from app.db.models import Game

GAME_NOT_FOUND = "Game not found."


def get_owned_game(
    game_id: str, user: CurrentUser, session: Annotated[Session, Depends(get_session)]
) -> Game:
    try:
        return get_game(session, user.id, game_id)
    except GameNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=GAME_NOT_FOUND) from error


OwnedGame = Annotated[Game, Depends(get_owned_game)]
