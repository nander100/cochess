# CLAUDE.md — CoChess

CoChess is a web app that coaches intermediate chess players (roughly 1000–1800 Elo) to improve. A user pastes a PGN, a chess engine analyzes the game, and an LLM coach (Claude API) explains the engine's findings in plain, encouraging language.

The full product spec lives in `SPEC.md`. **We are building v1 only.** v2–v4 are listed there so v1's design doesn't block them; do not implement them.

## The golden rule

**The engine analyzes. The LLM explains.**

- Stockfish decides how good a move or position is. python-chess detectors decide *what kind* of mistake it was.
- The LLM (coach) never calculates moves, never evaluates positions on its own, and never names a move that is not present in the data it was given.
- Every move the coach mentions is validated by the backend (see SPEC §7.4). If you find yourself writing code where the LLM is asked "what's the best move?", stop — that's wrong.

## Stack

- **Backend:** Python 3.12, FastAPI, python-chess, Anthropic Python SDK, SQLite via SQLAlchemy (Postgres later), Pydantic v2 for all schemas.
- **Frontend:** React + TypeScript + Vite. Stockfish runs in the browser (Stockfish.js / WASM) inside a Web Worker.
- **Packaging:** `uv` for Python, `npm` for the frontend, Docker Compose for running both.

## Repo layout

```
cochess/
├── CLAUDE.md
├── SPEC.md
├── docker-compose.yml
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware (COOP/COEP headers, access gate)
│   │   ├── config.py            # settings from env vars
│   │   ├── api/                 # route modules
│   │   ├── analysis/
│   │   │   ├── pgn.py           # PGN parsing + validation
│   │   │   ├── evals.py         # score normalization, win%, accuracy, classification
│   │   │   ├── material.py      # material counting, PV walking helpers
│   │   │   ├── detectors/       # one module per theme (SPEC §6)
│   │   │   └── summary.py       # builds the game summary
│   │   ├── coach/
│   │   │   ├── payload.py       # builds JSON sent to Claude
│   │   │   ├── prompts/         # system prompt .md files
│   │   │   ├── client.py        # Anthropic calls, streaming, usage logging
│   │   │   └── validate.py      # move-mention validation
│   │   └── db/                  # models + session
│   └── tests/
│       ├── fixtures/pgn/        # known games; fixtures/pgn/user/ = owner's real games
│       └── ...
└── frontend/
    ├── package.json
    └── src/
        ├── engine/              # stockfish worker wrapper, scan/verify/deep passes
        ├── api/                 # typed client for backend
        └── components/          # GameInput, ProgressBar, Synopsis, ChatPanel
```

Stockfish build: `stockfish-19-lite` (multi-threaded) with `stockfish-19-lite-single` fallback when `crossOriginIsolated` is false. The full builds ship a 99 MB wasm. Implementation plan and approved decisions: `docs/PLAN.md`.

## Commands

Backend (run from `backend/`):
- Install: `uv sync`
- Dev server: `uv run uvicorn app.main:create_app --factory --reload` (app factory: importing `app.main` has no side effects; tests build apps on in-memory SQLite via `tests/conftest.py`)
- Tests: `uv run pytest` (includes coverage; pytest plugin autoload is disabled in `pyproject.toml` so globally installed plugins, e.g. ROS on `PYTHONPATH`, can't break the run — add new pytest plugins there with `-p`)
- Lint/format: `uv run ruff check . && uv run ruff format .`
- Types: `uv run mypy app` (strict)
- Config: copy `.env.example` to `.env`. Nested settings use `__`, e.g. `THRESHOLDS__BLUNDER=0.35`.

Frontend (run from `frontend/`):
- Install: `npm install` (its `postinstall` copies the Stockfish lite builds into `public/engine/`, which is gitignored)
- Dev server: `npm run dev` (port 5173, sends COOP/COEP, proxies `/api` to `BACKEND_URL`, default `http://localhost:8000`)
- Tests: `npm test` (Vitest)
- Lint: `npm run lint` (oxlint, warnings fail)
- Types: `npm run typecheck`
- Build: `npm run build`
- E2E: `npm run e2e` (Playwright on the system Google Chrome via `channel: 'chrome'`, no browser download; starts its own backend on :8001 with in-memory SQLite and Vite on :5174; analyzes a real owner game with Stockfish and writes depth/time evidence to `test-results/m2-engine-evidence.json`. Pick the game with `E2E_GAME=game3w.txt`. Takes 40–90 s.)

Everything: `docker compose up --build` → http://localhost:8080 (nginx serves the frontend with COOP/COEP and proxies `/api` to the backend; SQLite lives in the `cochess-data` volume). Needs `backend/.env`.

Keep this section accurate. If a command changes, update it here.

## Conventions

- Python: type hints everywhere, Pydantic models for every request/response and every JSON payload sent to Claude. No untyped dicts crossing module boundaries.
- Evaluations are stored **from White's perspective** in centipawns (int) or mate-in-N (signed int). Convert from the engine's side-to-move score exactly once, in one function.
- Display format for evals: `+0.3`, `-2.0`, `+M3`, `-M2` (one decimal for centipawns).
- Plies are 1-indexed: ply 1 = White's first move. Move number = `(ply + 1) // 2`.
- All thresholds and engine settings live in config (SPEC §5.3 and §6.1), not scattered as magic numbers.
- Detectors are pure functions: `(context) -> list[ThemeFact]`. No I/O, no engine calls inside detectors.
- The Anthropic API key is backend-only. It never reaches the frontend, logs, or the repo.
- Model names come from env vars (`COACH_MODEL_SYNOPSIS`, `COACH_MODEL_CHAT`).

## Testing rules

- Every detector gets unit tests built from hand-made FEN positions where the answer is unambiguous (one positive case, one negative case minimum).
- PGN parsing tests cover: valid game, illegal move, non-standard start (`SetUp`/`FEN` header or Chess960 variant → rejected), variations/comments stripped, `%clk` preserved.
- Coach tests mock the Anthropic client. Never call the real API in tests.
- Don't mark a milestone done with failing tests, lint errors, or type errors.

## Checkpoints — stop and ask

The owner wants Claude Code to do the heavy lifting but to **stop for review** at the checkpoints listed in SPEC §10. At each checkpoint:
1. Summarize what was built and what's next.
2. Show evidence: test results, and for analysis/coach milestones, sample output on real fixture games.
3. Wait for approval before continuing.

Also stop and ask before: adding a dependency not named in this file, changing a data schema after it has been approved, or making any decision SPEC.md doesn't cover.

## Don't

- Don't let the LLM pick or evaluate moves.
- Don't invent puzzles, courses, or resources in coach output. Puzzle *genres* only, mapped to Lichess puzzle themes (SPEC §7.3).
- Don't build v2+ features (interactive board, accounts, payments, arrows) in v1.
- Don't accept PGNs from non-standard starting positions.
- Don't commit `.env`, API keys, or the SQLite database.

## Licensing note

Stockfish (and Stockfish.js) is GPL-3. Distributing it to users' browsers has GPL implications for the frontend. Keep frontend and backend cleanly separated so the backend can remain private. Flag any other GPL dependency before adding it.
