# CLAUDE.md — CoChess

CoChess is a web app that coaches intermediate chess players (roughly 1000–1800 Elo) to improve. Users upload games, a chess engine analyzes them, and an LLM coach (Claude API) explains the engine's findings in plain, encouraging language, teaches move by move, and tracks the player's tendencies over time.

- **Current work: v3.** The spec is `SPEC_V3.md`; the plan and decision log are `docs/PLAN_V3.md`.
- `SPEC.md` (v1) and `SPEC_V2.md` (v2) are kept for reference. `docs/v1-as-built.md` and `docs/v2-as-built.md` record what each version actually became; `docs/v2-handoff.md` records v2's deviations, feedback, known issues and gotchas.
- Where files disagree: `SPEC_V3.md` wins over older specs, `docs/PLAN_V3.md` decisions approved at a checkpoint win over the spec, and the code as built wins over all specs until a checkpoint decides otherwise.
- v4 is listed in `SPEC_V3.md` §13 so v3's design doesn't block it. Do not implement it.

## The golden rules

**1. The engine analyzes. The LLM explains.**
- Stockfish decides how good a move or position is. python-chess detectors decide *what kind* of mistake it was.
- The coach never calculates moves, never evaluates positions on its own, and never names a move that isn't in the data it was given.
- The backend validates every move the coach mentions. If you're writing code that asks the LLM "what's the best move?", stop.

**2. Withhold, don't instruct.**
- When the coach must not reveal something (any good-or-better move in an unsolved critical moment, or a walkthrough of its best line), leave it out of the payload.
- The leak check covers text, move tags, line links and annotations, but it's a backstop, not the main defense.

**3. Never trust the client for chess facts or identity.**
- The frontend sends move paths (UCI). The backend replays them with python-chess to get FENs, SAN, and PGN.
- Engine results come from the user's browser: check their FEN matches the replayed position, and never share or reuse them across users.
- Every user-data query is scoped by `user_id`.

**4. Every visual claim is checked.**
- Arrows and highlights from the coach are validated against python-chess and the engine data (SPEC_V3 §6.2) before they're drawn. Anything that fails is dropped and logged.
- Green arrows only ever mark moves the engine grades `best` or `good`.

## Stack

- **Backend:** Python 3.12, FastAPI, python-chess, Anthropic Python SDK, SQLAlchemy + Alembic, SQLite (Postgres in v4), Pydantic v2 for all schemas, httpx (game import only).
- **Frontend:** React + TypeScript + Vite, react-router, `@lichess-org/chessground` (board, including drawable auto-shapes; the old `chessground` package is deprecated), chess.js (legal moves and SAN while exploring on the board only), Stockfish.js (WASM) in a Web Worker, react-markdown (coach text, no raw HTML), Recharts (dashboard charts only).
- **Testing:** pytest, Vitest, Playwright (end-to-end and screenshots, with the engine and external APIs faked).
- **Packaging:** `uv` for Python, `npm` for the frontend, Docker Compose for both.

Ask before adding any dependency not listed here. State management uses React state/reducers; ask before adding a state library. Styling uses CSS custom properties for design tokens; ask before adding a CSS framework.

Stockfish build: `stockfish-19-lite` (multi-threaded) with `stockfish-19-lite-single` fallback when `crossOriginIsolated` is false. The full builds ship a 99 MB wasm.

## Repo layout (v3 additions marked +)

```
cochess/
├── CLAUDE.md
├── SPEC.md / SPEC_V2.md         # earlier specs (reference)
├── SPEC_V3.md                   # current spec
├── docs/
│   ├── v1-as-built.md, v2-as-built.md (+), v2-handoff.md
│   ├── PLAN.md, PLAN_V2.md      # earlier plans and decisions
│   ├── PLAN_V3.md               # + v3 plan, adjustments, decision log
│   └── DEPLOY.md                # single-server (EC2 + Caddy) deploy guide
├── docker-compose.yml
├── backend/
│   ├── alembic/                 # migrations
│   ├── app/
│   │   ├── main.py              # create_app() factory, middleware (COOP/COEP)
│   │   ├── config.py            # every threshold, engine tier, coach and limit setting (+ puzzle-theme mapping)
│   │   ├── cli.py               # create-user, invite, assign-games, backfill
│   │   ├── auth/                # invites, sessions, get_current_user
│   │   ├── api/                 # routes, schemas, sse
│   │   ├── analysis/
│   │   │   ├── pgn.py           # PGN parsing + validation
│   │   │   ├── pgn_export.py    # + export with variations, NAGs, evals, moment notes
│   │   │   ├── variations.py    # + saved-variation model and replay check
│   │   │   ├── paths.py         # replay UCI paths -> FEN/SAN/PGN
│   │   │   ├── engine.py        # EngineResult checks, UCI->SAN
│   │   │   ├── evals.py, accuracy.py, classify.py, selection.py, moves.py
│   │   │   ├── material.py, pawns.py, phase.py
│   │   │   ├── detectors/       # nine detectors
│   │   │   ├── move_facts.py    # + per-step facts for walkthroughs
│   │   │   ├── move_words.py    # + SAN to words for move tags
│   │   │   ├── settle.py        # + playback settle point and caption
│   │   │   ├── moments.py       # selection, grading, hints
│   │   │   ├── tendencies.py, onboarding.py, summary.py, summary_models.py
│   │   │   └── dashboard.py     # + dashboard aggregation
│   │   ├── coach/
│   │   │   ├── payload.py, client.py, service.py, chat.py, moments.py, baseline.py, tools.py
│   │   │   ├── prompts/         # coach_system.md (shared) + one file per task
│   │   │   ├── annotations.py   # + tag parsing and validation
│   │   │   ├── walkthrough.py   # + forced-tool walkthrough call
│   │   │   ├── markup.py        # + one pass over move tags, line links, board tags
│   │   │   ├── lines.py         # + line-link resolution from payload data
│   │   │   └── validate.py      # move validation + leak check (text, tags, annotations)
│   │   ├── importers/           # + lichess.py (Chess.com on hold)
│   │   └── db/                  # models, session, persistence helpers per area
│   ├── scripts/                 # print_summary, print_tendencies, synopsis, annotations_demo (owner tools)
│   └── tests/                   # fixtures/pgn/user = owner games, fixtures/engine = real results
└── frontend/
    ├── src/
    │   ├── styles/              # + design tokens, themes (v2: single styles.css)
    │   ├── ui/                  # + shared components
    │   ├── engine/              # worker wrapper, search control, tiers, live analysis
    │   ├── analysis/            # analysis pipeline, chat round trip, onboarding queue
    │   ├── board/               # chessground wrapper, game tree, move list, eval graph (+ annotations, saved variations, playback)
    │   ├── moments/             # critical-moment stepper
    │   ├── walkthrough/         # + stepper panel and useWalkthrough (the per-step scan lives in analysis/walkthrough.ts)
    │   ├── playback/            # + line playback hook and control bar (scans: analysis/playback.ts)
    │   ├── dashboard/           # + cards and charts
    │   ├── onboarding/          # paste-and-check table, slots, baseline report
    │   ├── components/          # ChatPanel, CoachText (markdown + board-tag icons), GameInput, Synopsis, ...
    │   ├── pages/               # Games, Analysis, Onboarding, Profile, Redeem, LatestGamePage (+ the nav's /analysis and /moments), GameOptions
    │   ├── shortcuts/           # + keyboard shortcuts and help overlay
    │   ├── theme/               # + light/dark/system theme state (ThemeProvider, useTheme)
    │   ├── api/                 # typed client, SSE reader, TS mirrors of backend schemas
    │   └── test/                # fake engine transport, scripted E2E engine, fakes
    └── e2e/                     # Playwright: flows/ (scripted engine + coach), analysis.spec.ts (real Stockfish)
```

If the real layout differs, follow the code and update this section.

## Commands

Backend (run from `backend/`):
- Install: `uv sync`
- Dev server: `uv run uvicorn app.main:create_app --factory --reload` (importing `app.main` has no side effects; tests build apps on in-memory SQLite via `tests/conftest.py`)
- Tests: `uv run pytest` (includes coverage; pytest plugin autoload is disabled in `pyproject.toml` — add new pytest plugins there with `-p`)
- Lint/format: `uv run ruff check . && uv run ruff format .`
- Types: `uv run mypy app` (strict)
- Config: copy `.env.example` to `.env`. Nested settings use `__`, e.g. `THRESHOLDS__BLUNDER=0.35`. Engine tiers can't be partly overridden (`EngineTier` fields have no defaults): override a whole tier, or set it in code as `tests/e2e_app.py` does.
- Migrations: `uv run alembic upgrade head` / `uv run alembic revision --autogenerate -m "..."`. The app also migrates at startup.
- Users: `uv run python -m app.cli create-user --name "..."`, `uv run python -m app.cli invite --user "..."` (prints a one-time `PUBLIC_BASE_URL/redeem#token=…` link), `uv run python -m app.cli assign-games --user "..."`, `uv run python -m app.cli backfill [--user "..."]` (rebuilds summaries from stored engine results, no engine runs; lists duplicate uploads without deleting). In Docker: `docker compose exec backend uv run --no-dev python -m app.cli …`.
- Optional per-player daily token cap: `USER_DAILY_TOKEN_LIMIT` (off by default).
- Owner tools (real games): `uv run python -m scripts.synopsis game5b --elo 800` (calls the Claude API), `uv run python -m scripts.annotations_demo game1w --db <scratch.db>` (real coach chat and moment replies with board tags, plus the annotation log, on a scratch database; calls the Claude API), `uv run python -m scripts.print_summary game1w [--elo 1400] [--compact]`, `uv run python -m scripts.print_tendencies --user "..."`.

Frontend (run from `frontend/`):
- Install: `npm install` (`postinstall` copies the Stockfish lite builds into `public/engine/`, gitignored)
- Dev server: `npm run dev` (port 5173, sends COOP/COEP, proxies `/api` to `BACKEND_URL`, default `http://localhost:8000`)
- Tests: `npm test` (Vitest)
- Lint: `npm run lint` (oxlint, warnings fail)
- Types: `npm run typecheck`
- Build: `npm run build`
- End-to-end: `npm run e2e` (= `npx playwright test`): flows in `e2e/flows/` on system Chrome against a scripted engine (`E2E_FAKE_ENGINE=1`) and scripted coach (`backend/tests/e2e_app.py`), own backend on :8001 with a fresh DB and Vite on :5174. `npm run e2e:real` runs real Stockfish on an owner game and **overwrites `backend/tests/fixtures/engine/<game>.json`** — `git restore` it unless you meant to re-capture.

Everything: `docker compose up --build` → http://localhost:8080 (`COCHESS_PORT` changes the host port; server deploys: `docs/DEPLOY.md`). Needs `backend/.env`.

Keep this section accurate. If a command changes, update it here.

## Conventions

- Python: type hints everywhere; Pydantic models for every request/response and every payload sent to Claude. No untyped dicts crossing module boundaries.
- Evals are stored from White's perspective: centipawns (int) or mate-in-N (signed int). The one conversion from the engine's side-to-move score is the frontend's `engine/score.ts::toWhitePov`; the backend never converts again. Terminal positions are never searched; the backend scores them from the board.
- Display evals as `+0.3`, `-2.0`, `+M3`, `-M2`. Graphs use win% from White's perspective.
- Engine tier settings live in backend config and reach the browser through `GET /api/engine-config`.
- Every engine result is checked by the backend before it's used: right position, every PV move legal.
- Coach replies are buffered and validated server-side before any text is streamed.
- Plies are 1-indexed: ply 1 = White's first move. Move number = `(ply + 1) // 2`.
- A board position is identified by its path: the list of UCI moves from the start position.
- All thresholds, engine settings, limits, and mappings live in config.
- Detectors and move-facts builders are pure functions: no I/O, no engine calls.
- Coach markup: move tags `{{move:Nxe5}}` (optionally numbered, `{{move:14...Qxd4}}`), line links `{{line:here.engine1|link text}}`, board tags `<board arrows="d1d4:red" squares="d4:red"/>`, and puzzle tags `{{puzzle:fork}}`. The backend parses, validates, and converts them to structured SSE events; the frontend never parses raw coach markup.
- Coach text uses everyday language (SPEC_V3 §9.2). Raw notation outside a move tag, or more than one move in a row in the text, is a validation failure. The coach never writes out a line; it links to one, and the backend fills in the moves.
- Line playback stops at the settle point computed on the backend (SPEC_V3 §9.6), never at a point chosen by the LLM.
- `user_color` is always chosen by the user: no default anywhere (schemas, forms, state, fixtures).
- Chat annotations refer to the position the message was sent from. Later positions are only annotated inside walkthroughs.
- Structured coach output (walkthroughs) uses a forced tool call, not free-text JSON.
- UI: no hard-coded colors, sizes, or fonts in components; use the design tokens (`frontend/src/styles/tokens.css`, from `docs/design/tokens.md`; `src/styles/tokens.guard.test.ts` fails on raw colors or font stacks). Fonts are self-hosted woff2 (OFL, licenses in `src/styles/fonts/`), never Google Fonts: the COEP header would block them. Themes: `<html data-theme="light|dark">`, light by default; "match system" is resolved in `src/theme/theme.ts`. Chess-meaning colors (good/inaccuracy/mistake/blunder/plan) come from one shared map and always appear with a glyph or label.
- States (SPEC_V3 §4.2): every page that loads data has a skeleton, an empty state that says what to do next, and an error state with a retry (`src/ui/Feedback.tsx`). Backend errors from an action show as a toast (`useToast`); a refusal about what the player typed (a bad PGN, a duplicate) stays inline next to the form. Coach replies show the typing indicator while they're checked.
- One prompt file per coach task where instructions differ; shared rules live in one base file.
- The Anthropic API key is backend-only and never logged. Model names come from env vars (`COACH_MODEL_SYNOPSIS`, `COACH_MODEL_CHAT`). `AnthropicCoachClient` takes the API key, not `Settings`.
- Session cookies: `httpOnly`, `SameSite=Lax`, `Secure` in production. Store only hashes of invite and session tokens. Invite tokens travel in the URL fragment.
- Games are deduplicated per player by fingerprint (players, result, UCI moves; no dates, no color). A second upload of the same game is a 409.
- Migrations: every schema change goes through Alembic. Never edit an applied migration. Data backfills are CLI commands, not migrations.
- No `×` or `–` in Python comments or docstrings (ruff RUF003). oxlint warnings fail the lint; it flags `setState` inside effects — derive state or use handlers.

## Testing rules

- Every detector, grading rule, hint builder, move-facts builder, and annotation rule gets unit tests from hand-built FENs (at least one positive and one negative case). Annotation tests cover each arrow type and color, including a green arrow on a bad move being rejected.
- Every user-data endpoint gets a test that another user's request returns 404.
- Leak tests: for each moment task before reveal, assert the payload has no withheld move, and the validator catches a leaked move in text, a move tag, a line link, or an annotation.
- Walkthrough tests: wrong step count, a move in the text that isn't in the line, and invalid step annotations are all caught.
- PGN export round-trips: export, re-import, replay, compare.
- Plain-language tests: bare notation and multi-move sequences in coach text are caught; move tags render the right words (captures, checks, castling, promotion); line references resolve, and `best` before reveal is rejected.
- Settle-point tests on hand-built lines: a piece win, an even exchange (never stops mid-exchange), a mate, and a quiet line.
- Color tests: the API rejects a missing color, and no color is selected when a form loads.
- The dashboard endpoint has a performance test with 200 generated games.
- Coach tests mock the Anthropic client (`tests/coach_fakes.py`); never call the real API in tests. Import tests fake the Lichess API. Frontend tests use the fake engine transport.
- Don't mark a milestone done with failing tests, lint errors, or type errors.

## Checkpoints — stop and ask

Stop for owner review at every ✅ checkpoint in SPEC_V3 §12. At each one:
1. Summarize what was built and what's next.
2. Show evidence: test results; for UI milestones, Playwright screenshots; for coach milestones, real output on the owner's games (with screenshots of annotations where relevant).
3. Wait for approval.

Also stop and ask before: adding a dependency not listed here, changing an approved schema, removing earlier behavior the spec doesn't mention, or making a decision the spec doesn't cover. Record decisions in `docs/PLAN_V3.md`.

## Gotchas

- Hooks: the Fact-Forcing Gate blocks the first Write of each new file until you state callers, no duplicate, data shape, and the user's instruction verbatim. A plugin hook reads `sed -n` in the same command as `git commit` as `--no-verify`; run commits on their own.
- The branch and tag are both named `v2`; use `refs/tags/v2` when it matters.
- The owner's local Docker app (compose project `cochcess`, port 8080) runs a pre-v2-M5 build with duplicate games. Ask before touching it.
- Playwright strict mode: text like "3. Ng5" appears in several places; scope locators.
- Deploy: see `docs/DEPLOY.md` and `docs/v2-handoff.md` (Caddy validate before reload, `COCHESS_PORT=127.0.0.1:8080`, exact `PUBLIC_BASE_URL`).

## Don't

- Don't let the LLM pick or evaluate moves.
- Don't put a withheld move in a payload, an arrow, a move tag, a line link, or a walkthrough before a moment is solved or revealed.
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
