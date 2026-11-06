"""Request validation errors in words a player can act on (SPEC_V3 §4.6)."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

COLOR_MESSAGE = "Choose the color you played: White or Black."
NOT_IN_GAME = f"Your username isn't in this game. {COLOR_MESSAGE}"


def color_needed(has_usernames: bool) -> HTTPException:
    """A game whose color wasn't given and couldn't be detected: the same shape as a missing
    `user_color`, so the form shows it next to the color choice."""
    message = NOT_IN_GAME if has_usernames else COLOR_MESSAGE
    detail = [{"loc": ["body", "user_color"], "msg": message, "type": "missing"}]
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _reworded(error: dict[str, Any]) -> dict[str, Any]:
    """A missing or invalid `user_color` gets a plain message; other errors are unchanged."""
    loc = error.get("loc", ())
    if loc and loc[-1] == "user_color":
        return {**error, "msg": COLOR_MESSAGE}
    return error


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [_reworded(dict(e)) for e in exc.errors()]
    # Color errors first: the frontend shows the first message.
    errors.sort(key=lambda e: e["msg"] != COLOR_MESSAGE)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _handle)
