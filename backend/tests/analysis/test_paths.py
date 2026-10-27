import pytest

from app.analysis.paths import PathError, movetext, position_key, resolve_path
from app.analysis.pgn import ParsedGame, parse_pgn
from tests.pgn_fixtures import read_pgn

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.fixture(scope="module")
def opera() -> ParsedGame:
    # 1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 ...
    return parse_pgn(read_pgn("opera_game.pgn"), max_chars=100_000, max_plies=600)


def test_the_start_position(opera: ParsedGame) -> None:
    path = resolve_path(opera, [], max_plies=600)

    assert (path.fen, path.ply, path.on_mainline, path.branch_ply) == (START, 0, True, None)
    assert (path.path_san, path.variation_san, path.pgn_to_move) == ([], [], "")


def test_a_mainline_position(opera: ParsedGame) -> None:
    path = resolve_path(opera, ["e2e4", "e7e5", "g1f3", "d7d6"], max_plies=600)

    assert path.on_mainline and path.branch_ply is None and path.variation_san == []
    assert path.path_san == ["e4", "e5", "Nf3", "d6"]
    assert path.pgn_to_move == "1. e4 e5 2. Nf3 d6"
    assert path.fen == opera.positions[4].fen_before
    assert path.ply == 4


def test_a_variation_records_where_it_left_the_game(opera: ParsedGame) -> None:
    # The game went 2...d6; the player tries 2...Nc6 3. Bb5.
    path = resolve_path(opera, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"], max_plies=600)

    assert not path.on_mainline
    assert path.branch_ply == 4  # ply 4 (2...Nc6) is the first move that differs
    assert path.variation_san == ["Nc6", "Bb5"]
    assert path.pgn_to_move == "1. e4 e5 2. Nf3 Nc6 3. Bb5"
    assert path.ply == 5


def test_a_variation_from_the_first_move(opera: ParsedGame) -> None:
    path = resolve_path(opera, ["d2d4"], max_plies=600)

    assert (path.on_mainline, path.branch_ply, path.variation_san) == (False, 1, ["d4"])


def test_castling_is_replayed_from_its_uci_king_move(opera: ParsedGame) -> None:
    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"]

    path = resolve_path(opera, moves, max_plies=600)

    assert path.path_san[-1] == "O-O"


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (["e2e5"], "Move 1 of the position (e2e5) isn't legal there."),
        (["e2e4", "e2e4"], "Move 2 of the position (e2e4) isn't legal there."),
        (["e2e4", "nonsense"], "Move 2 of the position isn't a valid move."),
        (["e7e5"], "Move 1 of the position (e7e5) isn't legal there."),  # Black can't start
    ],
)
def test_an_illegal_or_malformed_path_is_refused(
    opera: ParsedGame, path: list[str], message: str
) -> None:
    with pytest.raises(PathError) as error:
        resolve_path(opera, path, max_plies=600)

    assert error.value.message == message


def test_a_path_longer_than_the_limit_is_refused(opera: ParsedGame) -> None:
    with pytest.raises(PathError, match="too deep"):
        resolve_path(opera, ["e2e4", "e7e5", "g1f3"], max_plies=2)


def test_position_key_ignores_the_move_counters() -> None:
    assert position_key(START) == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
    assert position_key(START.replace(" 0 1", " 4 9")) == position_key(START)


def test_movetext_numbers_from_black() -> None:
    assert movetext(["d5", "Bf4", "Nf6"], first_ply=2) == "1... d5 2. Bf4 Nf6"
