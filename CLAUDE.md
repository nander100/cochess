# CLAUDE.md — CoChess

CoChess is a web app that coaches intermediate chess players (roughly 1000–1800 Elo) to improve. Users upload games, a chess engine analyzes them, and an LLM coach (Claude API) explains the engine's findings in plain, encouraging language and teaches move by move.

- **Current work: v2.** The spec is `SPEC_V2.md`.
- `SPEC.md` is the original v1 spec, kept for reference. `docs/v1-as-built.md` records what v1 actually became.
- Where the files disagree: `SPEC_V2.md` wins over `SPEC.md`, and the code as built wins over both until a checkpoint decides otherwise.
- v3–v4 are listed in `SPEC_V2.md` §14 so v2's design doesn't block them. Do not implement them.

## The golden rules

**1. The engine analyzes. The LLM explains.**
- Stockfish decides how good a move or position is. python-chess detectors decide *what kind* of mistake it was.
- The coach never calculates moves, never evaluates positions on its own, and never names a move that isn't in the data it was given.
- The backend validates every move the coach mentions. If you're writing code that asks the LLM "what's the best move?", stop.

**2. Withhold, don't instruct.**
- When the coach must not reveal something (the best move during a critical-moment exercise), leave it out of the payload. Never rely on the prompt alone to keep a secret.
- The leak check (SPEC_V2 §8.4) is a backstop, not the main defense.

**3. Never trust the client for chess facts or identity.**
- The frontend sends move paths (UCI). The backend replays them with python-chess to get FENs, SAN, and PGN.
- Engine results come from the user's browser: check their FEN matches the replayed position, and never share or reuse them across users.
- Every user-data query is scoped by `user_id`.

## Stack

- **Backend:** Python 3.12, FastAPI, python-chess, Anthropic Python SDK, SQLAlchemy + Alembic, SQLite (Postgres in v4), Pydantic v2 for all schemas.
- **Frontend:** React + TypeScript + Vite, react-router, chessground (board), chess.js (legal moves and SAN while exploring on the board only), Stockfish.js (WASM) in a Web Worker.
- **Testing:** pytest, Vitest, Playwright (end-to-end, with the engine faked).
- **Packaging:** `uv` for Python, `npm` for the frontend, Docker Compose for both.

Ask before adding any dependency not listed here. State management uses React state/reducers; ask before adding a state library.

## Repo layout (v2 additions marked +)

```
cochess/
├── CLAUDE.md
├── SPEC.md                      # v1 spec (reference)
├── SPEC_V2.md                   # current spec
├── docs/
│   ├── v1-as-built.md           # + written at v2 M0
│   ├── PLAN_V2.md               # + v2 implementation plan and decisions
│   ├── PLAN.md                  # v1 plan and approved v1 decisions (Q1–Q29)
│   └── DEPLOY.md                # single-server deploy guide
├── docker-compose.yml
├── backend/
│   ├── alembic/                 # + migrations
│   ├── app/
│   │   ├── main.py              # create_app() factory, middleware (COOP/COEP)
│   │   ├── config.py            # every threshold, engine tier, coach and limit setting
│   │   ├── cli.py               # + create-user, invite, assign-games, backfill
│   │   ├── auth/                # + invites, sessions, get_current_user
│   │   ├── api/                 # games, engine, coach (SSE) routes; schemas; sse helpers
│   │   ├── analysis/
│   │   │   ├── pgn.py           # PGN parsing + validation
│   │   │   ├── paths.py         # + replay UCI paths → FEN/SAN/PGN
│   │   │   ├── engine.py        # EngineResult schema, batch checks, UCI→SAN
│   │   │   ├── evals.py         # Evaluation, win%, format_eval
│   │   │   ├── accuracy.py      # Lichess accuracy
│   │   │   ├── classify.py      # classification, missed mate
│   │   │   ├── selection.py     # which plies get verified
│   │   │   ├── moves.py         # MoveContext/GameContext built from a game + results
│   │   │   ├── material.py, pawns.py, phase.py
│   │   │   ├── detectors/       # nine detectors (eight from SPEC + allowed_tactic)
│   │   │   ├── moments.py       # + selection, grading, hint builder
│   │   │   ├── tendencies.py    # + aggregation
│   │   │   ├── onboarding.py    # + slots, time-control categories
│   │   │   ├── summary.py       # builds the game summary
│   │   │   └── summary_models.py
│   │   ├── coach/
│   │   │   ├── payload.py       # payload models, coach view of the summary
│   │   │   ├── prompts/         # coach_system.md (shared) + one file per task
│   │   │   ├── client.py        # CoachClient protocol, Anthropic client, cached system blocks
│   │   │   ├── service.py       # synopsis
│   │   │   ├── chat.py          # chat + analyze_position round trip
│   │   │   ├── tools.py         # analyze_position input checks and tool result
│   │   │   └── validate.py      # move validation + moment leak check
│   │   └── db/                  # models, session, persistence helpers per area
│   ├── scripts/                 # print_summary, synopsis (owner tools, not the app)
│   └── tests/                   # fixtures/pgn/user = owner games, fixtures/engine = real results
└── frontend/
    └── src/
        ├── engine/              # worker wrapper, search control, tiers, live analysis
        ├── analysis/            # analysis pipeline (scan → verify), chat round trip
        ├── board/               # + chessground wrapper, game tree, move list, eval graph
        ├── moments/             # + critical-moment stepper
        ├── pages/               # + Games, Analysis, Onboarding, Profile, Redeem
        ├── components/          # v1 components (ChatPanel, Synopsis, ProgressBar, ...)
        ├── api/                 # typed client, SSE reader, TS mirrors of backend schemas
        └── test/                # fake engine transport, test helpers
```

If the real layout differs, follow the code and update this section.

Stockfish build: `stockfish-19-lite` (multi-threaded) with `stockfish-19-lite-single` fallback when `crossOriginIsolated` is false. The full builds ship a 99 MB wasm. The board package is `@lichess-org/chessground` (the old `chessground` npm package is deprecated).

## Commands

Backend (run from `backend/`):
- Install: `uv sync`
- Dev server: `uv run uvicorn app.main:create_app --factory --reload` (app factory: importing `app.main` has no side effects; tests build apps on in-memory SQLite via `tests/conftest.py`)
- Tests: `uv run pytest` (includes coverage; pytest plugin autoload is disabled in `pyproject.toml` so globally installed plugins, e.g. ROS on `PYTHONPATH`, can't break the run — add new pytest plugins there with `-p`)
- Lint/format: `uv run ruff check . && uv run ruff format .`
- Types: `uv run mypy app` (strict)
- Config: copy `.env.example` to `.env`. Nested settings use `__`, e.g. `THRESHOLDS__BLUNDER=0.35`.
- Migrations: `uv run alembic upgrade head` / `uv run alembic revision --autogenerate -m "..."`
- Users: `uv run python -m app.cli create-user --name "..."`, `uv run python -m app.cli invite --user "..."` (prints a one-time `PUBLIC_BASE_URL/redeem#token=…` link), `uv run python -m app.cli assign-games --user "..."` (gives ownerless v1 games to a player). In Docker: `docker compose exec backend uv run --no-dev python -m app.cli …`. The app also runs migrations itself at startup.
- Real synopsis for an owner game (calls the Claude API, needs `ANTHROPIC_API_KEY` in `.env`): `uv run python -m scripts.synopsis game5b --elo 800` (`--model`, `--effort` override; prints a cost estimate)
- Game summary for an owner game: `uv run python -m scripts.print_summary game1w [--elo 1400] [--compact]` (built from `tests/fixtures/engine/<game>.json`, real engine results captured by the frontend E2E)

Frontend (run from `frontend/`):
- Install: `npm install` (its `postinstall` copies the Stockfish lite builds into `public/engine/`, which is gitignored)
- Dev server: `npm run dev` (port 5173, sends COOP/COEP, proxies `/api` to `BACKEND_URL`, default `http://localhost:8000`)
- Tests: `npm test` (Vitest)
- Lint: `npm run lint` (oxlint, warnings fail)
- Types: `npm run typecheck`
- Build: `npm run build`
- End-to-end: `npm run e2e` (= `npx playwright test`; Playwright on the system Google Chrome via `channel: 'chrome'`, no browser download; starts its own backend on :8001 with in-memory SQLite and Vite on :5174. v1's E2E runs the real Stockfish on an owner game and **overwrites `backend/tests/fixtures/engine/<game>.json`** with that run's results; engine output varies run to run, so restore the committed fixture unless you mean to re-capture. `E2E_GAME=game3w.txt` picks the game. The coach (paid API) is off unless `E2E_COACH=1`; `E2E_QUESTIONS="a?|b?"` asks chat questions. The test logs in like a player: it creates one with the owner CLI against a fresh `test-results/e2e.db` (the E2E backend's database) and opens the printed link. `E2E_BASE_URL=http://localhost:8080` runs against a running stack; then pass a link from `app.cli invite` in `E2E_LOGIN_LINK`. Outputs go to `test-results/`. Takes 40–90 s. v2's M7 adds engine-faked flows.)

Everything: `docker compose up --build` → http://localhost:8080 (`COCHESS_PORT` changes the host port; server deploys: `docs/DEPLOY.md`). nginx serves the frontend with COOP/COEP and proxies `/api`; SQLite lives in the `cochess-data` volume. Needs `backend/.env`.

Keep this section accurate. If a command changes, update it here.

## Conventions

- Python: type hints everywhere; Pydantic models for every request/response and every payload sent to Claude. No untyped dicts crossing module boundaries.
- Evals are stored from White's perspective: centipawns (int) or mate-in-N (signed int). The one conversion from the engine's side-to-move score is the frontend's `engine/score.ts::toWhitePov`; the backend never converts again. Terminal positions (mate/stalemate) are never searched; the backend scores them from the board.
- Display evals as `+0.3`, `-2.0`, `+M3`, `-M2` (one decimal; `0.0` for zero). Graphs use win% from White's perspective.
- Engine tier settings live in backend config and reach the browser through `GET /api/engine-config`; the frontend never hard-codes them.
- Every engine result is checked by the backend before it's stored: it must be for a position the backend expects, and every PV move must be legal (python-chess).
- Coach replies are buffered and move-validated server-side before any text is streamed (SSE events: `status`, `text`, `done`, `error`, `engine_request`; keepalive comments while waiting).
- Plies are 1-indexed: ply 1 = White's first move. Move number = `(ply + 1) // 2`.
- A board position is identified by its path: the list of UCI moves from the start position.
- All thresholds, engine settings, decay half-life, moment limits, and attempt counts live in config.
- Detectors are pure functions `(context) -> list[ThemeFact]`: no I/O, no engine calls.
- One prompt file per coach task where instructions differ; shared rules live in one base file.
- The Anthropic API key is backend-only and never logged. Model names come from env vars (`COACH_MODEL_SYNOPSIS`, `COACH_MODEL_CHAT`).
- Session cookies: `httpOnly`, `SameSite=Lax`, `Secure` in production. Store only hashes of invite and session tokens.
- Migrations: every schema change goes through Alembic. Never edit an applied migration.

## Testing rules

- Every detector, grading rule, and hint builder gets unit tests from hand-built FENs (at least one positive and one negative case).
- Every user-data endpoint gets a test that another user's request returns 404.
- Path replay tests: legal paths, illegal paths, paths into variations.
- PGN parsing tests cover: valid game, illegal move, non-standard start (`SetUp`/`FEN` header or Chess960 variant → rejected), variations/comments stripped, `%clk` preserved.
- Leak tests: for each moment task before reveal, assert the payload has no best move and the validator catches a leaked one.
- Tendency math is tested with hand-computed expected values.
- Coach tests mock the Anthropic client; never call the real API in tests. Frontend tests use the fake engine transport.
- Don't mark a milestone done with failing tests, lint errors, or type errors.

## Checkpoints — stop and ask

Stop for owner review at every ✅ checkpoint in SPEC_V2 §13. At each one:
1. Summarize what was built and what's next.
2. Show evidence: test results, and for analysis/coach milestones, real output on the owner's games (including payloads where the milestone asks for them).
3. Wait for approval.

Also stop and ask before: adding a dependency not listed here, changing an approved schema, deleting or rewriting v1 behavior the spec doesn't mention, or making a decision the spec doesn't cover.

## Don't

- Don't let the LLM pick or evaluate moves.
- Don't put the best move in a payload before a moment is solved or revealed.
- Don't trust FENs, SAN, or engine results from the client without checking them.
- Don't invent puzzles, courses, or resources. Puzzle themes only, from the allowed list.
- Don't build v3+ features (dashboard charts, coach-drawn arrows, line stepping, game import, Google sign-in, payments).
- Don't accept PGNs from non-standard starting positions.
- Don't commit `.env`, API keys, the SQLite database, or invite links.

## Licensing note

Stockfish.js and chessground are GPL-3. Shipping them to browsers has GPL implications for the frontend. Keep the frontend and backend cleanly separated so the backend can stay private. Flag any other GPL dependency before adding it.