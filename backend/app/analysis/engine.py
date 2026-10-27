"""Engine results posted by the browser (SPEC §5.4), and checks that they fit the game."""

from collections.abc import Collection, Mapping, Sequence
from typing import Literal, Self

import chess
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analysis.evals import Evaluation, terminal_evaluation
from app.analysis.paths import position_key
from app.analysis.pgn import ParsedGame
from app.config import EngineTier

Tier = Literal["scan", "verify", "deep"]
TIER_RANK: dict[Tier, int] = {"scan": 0, "verify": 1, "deep": 2}


class EngineLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    eval_cp: int | None = None  # White POV
    mate: int | None = None  # White POV; positive = White mates
    moves_uci: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def exactly_one_score(self) -> Self:
        if (self.eval_cp is None) == (self.mate is None):
            raise ValueError("exactly one of eval_cp and mate must be set")
        if self.mate == 0:
            raise ValueError("mate must be non-zero")
        return self

    def evaluation(self) -> Evaluation:
        return Evaluation(cp=self.eval_cp) if self.mate is None else Evaluation(mate=self.mate)


class EngineResult(BaseModel):
    """One engine search. `fen` is the position searched; `ply` is informational."""

    model_config = ConfigDict(frozen=True)

    ply: int | None = Field(default=None, ge=1)
    fen: str
    tier: Tier
    depth: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    lines: list[EngineLine] = Field(min_length=1)

    @model_validator(mode="after")
    def ranks_are_one_to_n(self) -> Self:
        if [line.rank for line in self.lines] != list(range(1, len(self.lines) + 1)):
            raise ValueError("lines must be ordered by rank 1..n")
        return self

    def evaluation(self) -> Evaluation:
        return self.lines[0].evaluation()


class EngineResultError(Exception):
    """A batch of engine results doesn't fit the game. `message` is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def check_batch(
    results: Sequence[EngineResult],
    *,
    tier: Tier,
    tier_config: EngineTier,
    expected_fens: Collection[str],
) -> list[EngineResult]:
    """Validate a batch against the positions we asked for. Returns results with lines truncated.

    The batch must cover exactly `expected_fens`, once each, so arbitrary positions can't be
    stored against a game.
    """
    fens = [result.fen for result in results]
    if len(set(fens)) != len(fens):
        raise EngineResultError("Each position may only be submitted once.")
    unexpected = set(fens) - set(expected_fens)
    if unexpected:
        raise EngineResultError(f"{len(unexpected)} result(s) are for positions not requested.")
    missing = set(expected_fens) - set(fens)
    if missing:
        raise EngineResultError(f"Missing engine results for {len(missing)} position(s).")
    return [_check_result(result, tier=tier, tier_config=tier_config) for result in results]


def check_for_position(
    result: EngineResult, *, fen: str, tier_configs: Mapping[Tier, EngineTier]
) -> EngineResult:
    """Validate a result the browser sent for one position (chat, Explain): it must be for `fen`
    (the position the backend replayed from the path, compared without move counters), of an
    allowed tier, with legal lines. Returns it with lines truncated to the tier's length."""
    if position_key(result.fen) != position_key(fen):
        raise EngineResultError("The engine result is for a different position than the board.")
    config = tier_configs.get(result.tier)
    if config is None:
        allowed = " or ".join(tier_configs)
        raise EngineResultError(f"Expected a {allowed} result, got {result.tier}.")
    return _check_result(
        result.model_copy(update={"fen": fen}), tier=result.tier, tier_config=config
    )


def _check_result(result: EngineResult, *, tier: Tier, tier_config: EngineTier) -> EngineResult:
    if result.tier != tier:
        raise EngineResultError(f"Expected {tier} results, got {result.tier}.")
    if len(result.lines) > tier_config.multipv:
        raise EngineResultError(f"At most {tier_config.multipv} line(s) per {tier} result.")
    lines = [
        line.model_copy(update={"moves_uci": line.moves_uci[: tier_config.max_line_plies]})
        for line in result.lines
    ]
    for line in lines:
        _check_line_is_legal(result.fen, line.moves_uci)
    return result.model_copy(update={"lines": lines})


def _check_line_is_legal(fen: str, moves_uci: Sequence[str]) -> None:
    board = chess.Board(fen)
    for uci in moves_uci:
        try:
            move = chess.Move.from_uci(uci)
        except chess.InvalidMoveError as error:
            raise EngineResultError(f"Engine line contains an invalid move: {uci}.") from error
        if move not in board.legal_moves:
            raise EngineResultError(f"Engine line contains an illegal move: {uci}.")
        board.push(move)


def uci_line_to_san(fen: str, moves_uci: Sequence[str]) -> list[str]:
    """Convert a (validated) engine line to SAN with python-chess."""
    board = chess.Board(fen)
    sans = []
    for uci in moves_uci:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)
    return sans


def best_by_fen(results: Sequence[EngineResult]) -> dict[str, EngineResult]:
    """Keep the highest-tier result per position (verified results replace scan results)."""
    best: dict[str, EngineResult] = {}
    for result in results:
        current = best.get(result.fen)
        if current is None or TIER_RANK[result.tier] > TIER_RANK[current.tier]:
            best[result.fen] = result
    return best


def position_evaluations(game: ParsedGame, by_fen: dict[str, EngineResult]) -> list[Evaluation]:
    """Evaluation of every position: before each ply, then the final position.

    A terminal final position is evaluated from the board, not the engine (PLAN Q8).
    """
    evals = [by_fen[p.fen_before].evaluation() for p in game.positions]
    terminal = terminal_evaluation(chess.Board(game.final_fen)) if game.final_is_terminal else None
    evals.append(terminal or by_fen[game.final_fen].evaluation())
    return evals
