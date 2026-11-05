# CLAUDE.md — CoChess

CoChess is a web app that coaches intermediate chess players (roughly 1000–1800 Elo) to improve. Users upload games, a chess engine analyzes them, and an LLM coach (Claude API) explains the engine's findings in plain, encouraging language, teaches move by move, and tracks the player's tendencies over time.

- **Current work: v3.** The spec is `SPEC_V3.md`.
- `SPEC.md` (v1) and `SPEC_V2.md` (v2) are kept for reference. `docs/v1-as-built.md` and `docs/v2-as-built.md` record what each version actually became.
- Where files disagree: `SPEC_V3.md` wins over older specs, and the code as built wins over all specs until a checkpoint decides otherwise.
- v4 is listed in `SPEC_V3.md` §13 so v3's design doesn't block it. Do not implement it.

## The golden rules

**1. The engine analyzes. The LLM explains.**
- Stockfish decides how good a move or position is. python-chess detectors decide *what kind* of mistake it was.
- The coach never calculates moves, never evaluates positions on its own, and never names a move that isn't in the data it was given.
- The backend validates every move the coach mentions. If you're writing code that asks the LLM "what's the best move?", stop.

**2. Withhold, don't instruct.**
- When the coach must not reveal something (the best move in an unsolved critical moment, or a walkthrough of its best line), leave it out of the payload.
- The leak check covers text and annotations, but it's a backstop, not the main defense.

**3. Never trust the client for chess facts or identity.**
- The frontend sends move paths (UCI). The backend replays them with python-chess to get FENs, SAN, and PGN.
- Engine results come from the user's browser: check their FEN matches the replayed position, and never share or reuse them across users.
- Every user-data query is scoped by `user_id`.

**4. Every visual claim is checked.**
- Arrows and highlights from the coach are validated against python-chess and the engine data (SPEC_V3 §6.2) before they're drawn. Anything that fails is dropped and logged.
- Green arrows only ever mark moves the engine grades `best` or `good`.

## Stack

- **Backend:** Python 3.12, FastAPI, python-chess, Anthropic Python SDK, SQLAlchemy + Alembic, SQLite (Postgres in v4), Pydantic v2 for all schemas, httpx (game import only).
- **Frontend:** React + TypeScript + Vite, react-router, chessground (board, including drawable auto-shapes), chess.js (legal moves and SAN while exploring on the board only), Stockfish.js (WASM) in a Web Worker, Recharts (dashboard charts only).
- **Testing:** pytest, Vitest, Playwright (end-to-end and screenshots, with the engine and external APIs faked).
- **Packaging:** `uv` for Python, `npm` for the frontend, Docker Compose for both.

Ask before adding any dependency not listed here. State management uses React state/reducers; ask before adding a state library. Styling uses CSS custom properties for design tokens; ask before adding a CSS framework.

## Repo layout (v3 additions marked +)

```
cochess/
├── CLAUDE.md
├── SPEC.md / SPEC_V2.md         # earlier specs (reference)
├── SPEC_V3.md                   # current spec
├── docs/v1-as-built.md
├── docs/v2-as-built.md          # + written at v3 M0
├── docker-compose.yml
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py            # + puzzle-theme mapping table
│   │   ├── cli.py
│   │   ├── auth/
│   │   ├── api/
│   │   ├── analysis/
│   │   │   ├── pgn.py           # + PGN export with variations, NAGs, evals
│   │   │   ├── paths.py
│   │   │   ├── evals.py
│   │   │   ├── detectors/
│   │   │   ├── move_facts.py    # + per-step facts for walkthroughs
│   │   │   ├── moments.py
│   │   │   ├── tendencies.py
│   │   │   ├── dashboard.py     # + dashboard aggregation
│   │   │   ├── onboarding.py
│   │   │   └── summary.py
│   │   ├── coach/
│   │   │   ├── payload.py
│   │   │   ├── prompts/
│   │   │   ├── client.py
│   │   │   ├── annotations.py   # + tag parsing and validation
│   │   │   ├── walkthrough.py   # + forced-tool walkthrough call
│   │   │   └── validate.py      # move validation + leak check (text and annotations)
│   │   ├── importers/           # + lichess.py, chesscom.py (if M7 is approved)
│   │   └── db/
│   └── tests/
└── frontend/
    └── src/
        ├── styles/              # + design tokens, themes
        ├── ui/                  # + shared components
        ├── engine/
        ├── board/               # + annotation drawing, saved variations
        ├── moments/
        ├── walkthrough/         # + stepper
        ├── dashboard/           # + dashboard cards and charts
        ├── pages/               # + Dashboard, Settings
        ├── shortcuts/           # + keyboard shortcuts and help overlay
        ├── api/
        └── test/                # fake engine transport, fake external APIs
```

If the real layout differs, follow the code and update this section.

## Commands

Backend (run from `backend/`):
- Install: `uv sync`
- Dev server: `uv run uvicorn app.main:app --reload`
- Tests: `uv run pytest`
- Lint/format: `uv run ruff check . && uv run ruff format .`
- Types: `uv run mypy app`
- Migrations: `uv run alembic upgrade head` / `uv run alembic revision --autogenerate -m "..."`
- Users: `uv run python -m app.cli create-user --name "..."`, `uv run python -m app.cli invite --user "..."`

Frontend (run from `frontend/`):
- Install: `npm install`
- Dev server: `npm run dev`
- Tests: `npm test` (Vitest)
- End-to-end: `npx playwright test`
- Lint: `npm run lint`

Everything: `docker compose up --build`

Keep this section accurate. If a command changes, update it here.

## Conventions

- Python: type hints everywhere; Pydantic models for every request/response and every payload sent to Claude.
- Evals are stored from White's perspective: centipawns (int) or mate-in-N (signed int). Convert from the engine's side-to-move score once, in one function.
- Display evals as `+0.3`, `-2.0`, `+M3`, `-M2`. Graphs use win% from White's perspective.
- Plies are 1-indexed: ply 1 = White's first move. Move number = `(ply + 1) // 2`.
- A board position is identified by its path: the list of UCI moves from the start position.
- All thresholds, engine settings, limits, and mappings live in config.
- Detectors and move-facts builders are pure functions: no I/O, no engine calls.
- Coach markup: move tags `{{move:Nxe5}}`, line links `{{line:here.engine1|link text}}`, board tags `<board arrows="d1d4:red" squares="d4:red"/>`, and puzzle tags `{{puzzle:fork}}`. The backend parses, validates, and converts them to structured SSE events; the frontend never parses raw coach markup.
- Coach text uses everyday language (SPEC_V3 §9.2). Raw notation outside a move tag, or more than one move in a row in the text, is a validation failure. The coach never writes out a line; it links to one, and the backend fills in the moves.
- Line playback stops at the settle point computed on the backend (SPEC_V3 §9.6), never at a point chosen by the LLM.
- `user_color` is always chosen by the user: no default anywhere (schemas, forms, state, fixtures).
- Chat annotations refer to the position the message was sent from. Later positions are only annotated inside walkthroughs.
- Structured coach output (walkthroughs) uses a forced tool call, not free-text JSON.
- UI: no hard-coded colors, sizes, or fonts in components; use the design tokens. Chess-meaning colors (good/inaccuracy/mistake/blunder/plan) come from one shared map and always appear with a glyph or label.
- One prompt file per coach task where instructions differ; shared rules live in one base file.
- The Anthropic API key is backend-only and never logged. Model names come from env vars (`COACH_MODEL_SYNOPSIS`, `COACH_MODEL_CHAT`).
- Session cookies: `httpOnly`, `SameSite=Lax`, `Secure` in production. Store only hashes of invite and session tokens.
- Migrations: every schema change goes through Alembic. Never edit an applied migration.

## Testing rules

- Every detector, grading rule, hint builder, move-facts builder, and annotation rule gets unit tests from hand-built FENs (at least one positive and one negative case). Annotation tests cover each arrow type and color, including a green arrow on a bad move being rejected.
- Every user-data endpoint gets a test that another user's request returns 404.
- Leak tests: for each moment task before reveal, assert the payload has no best move, and the validator catches a leaked move in text or in an annotation.
- Walkthrough tests: wrong step count, a move in the text that isn't in the line, and invalid step annotations are all caught.
- PGN export round-trips: export, re-import, replay, compare.
- Plain-language tests: bare notation and multi-move sequences in coach text are caught; move tags render the right words (captures, checks, castling, promotion); line references resolve, and `best` before reveal is rejected.
- Settle-point tests on hand-built lines: a piece win, an even exchange (never stops mid-exchange), a mate, and a quiet line.
- Color tests: the API rejects a missing color, and no color is selected when a form loads.
- The dashboard endpoint has a performance test with 200 generated games.
- Coach tests mock the Anthropic client; never call the real API in tests. Import tests fake the Lichess and Chess.com APIs. Frontend tests use the fake engine transport.
- Don't mark a milestone done with failing tests, lint errors, or type errors.

## Checkpoints — stop and ask

Stop for owner review at every ✅ checkpoint in SPEC_V3 §12. At each one:
1. Summarize what was built and what's next.
2. Show evidence: test results; for UI milestones, Playwright screenshots; for coach milestones, real output on the owner's games (with screenshots of annotations where relevant).
3. Wait for approval.

Also stop and ask before: adding a dependency not listed here, changing an approved schema, removing earlier behavior the spec doesn't mention, or making a decision the spec doesn't cover.

## Don't

- Don't let the LLM pick or evaluate moves.
- Don't put the best move in a payload, an arrow, or a walkthrough before a moment is solved or revealed.
- Don't draw an annotation that hasn't passed validation.
- Don't trust FENs, SAN, or engine results from the client without checking them.
- Don't invent puzzles, courses, or resources. Puzzle themes only, from the allowed list, as validated tags.
- Don't build v4 features (Google sign-in, payments, credits, production AWS setup, mobile layout).
- Don't accept PGNs from non-standard starting positions.
- Don't default the user's color to White (or anything).
- Don't let the coach write out move sequences; use line links.
- Don't commit `.env`, API keys, the SQLite database, or invite links.

## Licensing note

Stockfish.js and chessground are GPL-3. Shipping them to browsers has GPL implications for the frontend. Keep the frontend and backend cleanly separated so the backend can stay private. Check the license of any piece set or board theme before adding it, and flag any other GPL dependency first.
