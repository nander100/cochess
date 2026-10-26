from pathlib import Path
from typing import Literal

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pgn"
USER_DIR = FIXTURE_DIR / "user"
# Owner's games: one game per file, named like `game1w.txt` / `game2b.pgn` (last letter = the
# color the owner played).
USER_FIXTURES = sorted([*USER_DIR.glob("*.pgn"), *USER_DIR.glob("*.txt")])
OWNER_USERNAME = "nander100"


def read_pgn(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def owner_color(path: Path) -> Literal["white", "black"]:
    suffix = path.stem[-1].lower()
    if suffix == "w":
        return "white"
    if suffix == "b":
        return "black"
    raise ValueError(f"{path.name}: name must end in 'w' or 'b' (the color the owner played)")
