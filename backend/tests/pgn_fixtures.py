from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pgn"
USER_FIXTURES = sorted((FIXTURE_DIR / "user").glob("*.pgn"))


def read_pgn(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()
