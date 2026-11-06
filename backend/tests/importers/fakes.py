"""Fake Lichess and Chess.com APIs for tests (httpx.MockTransport): no real network calls."""

import json
from collections.abc import Callable
from typing import Any

import httpx

PGN = (
    '[Event "Rated game"]\n[White "{white}"]\n[Black "{black}"]\n[Result "1-0"]\n'
    '[TimeControl "600"]\n\n1. {move} e5 1-0'
)
MOVES = ["e4", "d4", "c4", "Nf3", "g3", "b3", "f4", "Nc3"]


def pgn(n: int, white: str = "me", black: str | None = None) -> str:
    """A distinct short game (its first move and opponent differ by `n`)."""
    return PGN.format(white=white, black=black or f"Rival{n}", move=MOVES[n % len(MOVES)])


Handler = Callable[[httpx.Request], httpx.Response]


def recording(handler: Handler) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), seen


def lichess_games(*games: dict[str, Any]) -> Handler:
    body = "\n".join(json.dumps(g) for g in games) + "\n"
    return lambda request: httpx.Response(200, text=body)


def lichess_game(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"lc{n:06}",
        "variant": "standard",
        "lastMoveAt": 1_761_400_000_000 + n,
        "pgn": pgn(n),
        **extra,
    }


def chesscom_api(archives: dict[str, list[dict[str, Any]]], user: str = "me") -> Handler:
    """Archives by month ("2026/10"), each with its games oldest first, as Chess.com sends them."""
    base = f"https://api.chess.com/pub/player/{user}/games"

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{base}/archives":
            return httpx.Response(200, json={"archives": [f"{base}/{m}" for m in sorted(archives)]})
        month = url.removeprefix(f"{base}/")
        if month in archives:
            return httpx.Response(200, json={"games": archives[month]})
        return httpx.Response(404, json={"message": "not found"})

    return handle


def chesscom_game(n: int, end_time: int = 1_761_400_000, **extra: Any) -> dict[str, Any]:
    return {
        "url": f"https://www.chess.com/game/live/{1000 + n}",
        "pgn": pgn(n),
        "time_class": "rapid",
        "rules": "chess",
        "end_time": end_time + n,
        **extra,
    }
