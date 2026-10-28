# CoChess

An AI chess coach for intermediate players (roughly 1000–1800 Elo). Paste a game in PGN; Stockfish analyzes every move in your browser, rule-based detectors work out what *kind* of mistakes you made, and a Claude-powered coach explains it all in plain, encouraging language. Then ask follow-up questions, including "what if I had played X?", which the engine analyzes on the spot.

**The golden rule: the engine analyzes, the coach explains.** Stockfish decides how good every move is. The coach reasons about the position, but every move it writes is checked against the engine's data before you see it, and anything it can't back up is removed.

## How it works

1. **Log in** with a one-time link from the owner, then fill in your profile: rating, the time control you play most, and (optionally) your style.
2. **Onboarding assessment (optional).** Paste 12 games in your main time control: 3 wins and 3 losses with each color. CoChess checks which slot each fills, analyzes them one by one in your browser (about 10 minutes; closing the tab and coming back picks up where it stopped), and your coach writes a **baseline report**: your strengths, the top 3 things to work on with examples from your games, how your openings are going, and a 2–4 week plan. It's kept on your profile.
3. **Analyze any game.** Paste a PGN. Stockfish (WASM, multi-threaded where the browser allows) **scans** every position, then **verifies** the moments that matter with a deeper 4-line search. The backend classifies every move (Lichess winning-chances model), computes Lichess-style accuracy, and runs nine theme detectors (hung piece, allowed tactic, missed tactic, missed capture/check, king safety, pawn structure, endgame technique, slow development, time trouble).
4. **The analysis board.** Step through the game with the arrow keys, see the eval graph and a live engine panel, and play your own variations on the board.
5. **Your coach** (Claude) writes a short synopsis, answers questions about whatever position is on the board, including your own variations, and explains a position on request. When a question needs analysis the game doesn't have, the coach asks your browser's engine for a deeper look first.
6. **Critical moments.** Your biggest mistakes become exercises: find a better move yourself, get graded by the engine, get hints if you're stuck, then see the engine's move. The coach never sees the answer before you've found it or asked for it.
7. **Tendencies.** Your mistake themes are tracked across games, recent games counting most, so the coach can say "this is the third game where a loose knight cost you material".

Specs: [`SPEC_V2.md`](SPEC_V2.md) (current) and [`SPEC.md`](SPEC.md) (v1). Implementation plans and every design decision: [`docs/PLAN_V2.md`](docs/PLAN_V2.md) and [`docs/PLAN.md`](docs/PLAN.md). Conventions and commands for contributors: [`CLAUDE.md`](CLAUDE.md).

## Quick start (Docker)

You need Docker with Compose and an [Anthropic API key](https://platform.claude.com/).

```bash
cp backend/.env.example backend/.env
# Edit backend/.env: set ANTHROPIC_API_KEY to your key, and PUBLIC_BASE_URL=http://localhost:8080.
docker compose up --build
docker compose exec backend uv run --no-dev python -m app.cli create-user --name "Alex"
docker compose exec backend uv run --no-dev python -m app.cli invite --user Alex
```

Open the login link it prints, fill in your profile, then do the onboarding assessment or skip it and paste a game.

To put it on a server for your testers, follow [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Configuration

Settings come from `backend/.env` (never commit it). Nested settings use `__`.

| Variable | Default | What it does |
|---|---|---|
| `PUBLIC_BASE_URL` | `http://localhost:5173` | Where players open CoChess; `app.cli invite` builds login links from it. |
| `AUTH__COOKIE_SECURE` | `true` | Session cookies only over HTTPS (browsers also accept them on `http://localhost`). |
| `ANTHROPIC_API_KEY` | *(empty)* | Needed for the coach. Without it, analysis still works and the coach panel says it isn't set up. |
| `COACH_MODEL_SYNOPSIS` | `claude-sonnet-5-5` | Model for the synopsis (low effort). `claude-opus-5-5` writes deeper synopses at about 2× the cost. |
| `COACH_MODEL_CHAT` | `claude-haiku-5-5` | Model for the chat. `claude-sonnet-5-5` reasons more carefully at about 20× the cost per message. |
| `DATABASE_URL` | `sqlite:///./cochess.db` | Docker overrides it to a file on the `cochess-data` volume. |
| `LIMITS__MAX_GAMES_PER_DAY` | `10` | New single games per player per rolling 24 hours (onboarding games don't count). |
| `USER_DAILY_TOKEN_LIMIT` | *(off)* | Claude tokens one player may use in a rolling 24 hours; past it, coach requests are refused until the next day. |
| `COACH__CHAT_MAX_MESSAGES` | `30` | Questions per game (chat and critical moments together). |
| `COACH__SYNOPSIS_EFFORT`, `COACH__CHAT_EFFORT` | `low`, `medium` | Claude effort level (`low` … `max`): trades depth for speed and cost. |
| `THRESHOLDS__INACCURACY` / `__MISTAKE` / `__BLUNDER` | `0.10` / `0.20` / `0.30` | Winning-chances drop for each label. |
| `COCHESS_PORT` | `8080` | Host port for `docker compose` (an env var for compose, not in `backend/.env`). |

Every threshold, engine tier, and detector setting lives in [`backend/app/config.py`](backend/app/config.py).

## Development

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22+, and Google Chrome (for the end-to-end tests).

```bash
# Backend (from backend/)
uv sync
cp .env.example .env            # fill in what you need
uv run uvicorn app.main:create_app --factory --reload

# Frontend (from frontend/) — in another terminal
npm install                     # also copies the Stockfish builds into public/engine/
npm run dev                     # http://localhost:5173, proxies /api to the backend
```

### Checks

```bash
# Backend (from backend/)
uv run pytest                   # unit + API tests, with coverage
uv run ruff check . && uv run ruff format .
uv run mypy app

# Frontend (from frontend/)
npm test                        # Vitest
npm run lint && npm run typecheck
npm run build
```

### End-to-end tests

`npm run e2e` (from `frontend/`) drives the real backend and frontend in your installed Chrome, with a **scripted engine** (real chess rules, material-only evaluation) and a **scripted coach**: free, the same every run, about 40 seconds. It covers login → upload → board → synopsis, chat and Explain → a critical moment; onboarding through the baseline report (with a reload mid-analysis); and the error states (used login link, illegal or non-standard PGN, duplicate upload, another player's game).

`npm run e2e:real` runs the original test instead: real Stockfish on one of the owner's games (40–90 seconds), with the coach off unless you ask for it, because it calls the paid API.

```bash
npm run e2e                                         # scripted engine and coach, free
npm run e2e:real                                    # real Stockfish, no coach
E2E_GAME=game3w.txt npm run e2e:real                # another game
E2E_COACH=1 npm run e2e:real                        # + a real synopsis (~$0.02)
E2E_BASE_URL=http://localhost:8080 E2E_LOGIN_LINK=<link from app.cli invite> npm run e2e:real   # against docker compose
```

Outputs go to `frontend/test-results/`. `npm run e2e:real` also rewrites `backend/tests/fixtures/engine/<game>.json` with that run's engine results; restore the committed file unless you mean to re-capture it.

Owner scripts for tuning analysis on real games (from `backend/`):

```bash
uv run python -m scripts.print_summary game1w --compact   # the summary the coach sees
uv run python -m scripts.synopsis game5b --elo 1400       # a real synopsis (calls the API)
uv run python -m scripts.print_tendencies --user "Alex"   # tendencies with the math shown
```

## Cost

With the default models, a game costs about **$0.02**: the synopsis (Claude Sonnet 5.5 at low effort, about 4.7k input / 0.7k output tokens) plus well under a cent per chat question or critical-moment step (Claude Haiku 5.5). The baseline report is one Sonnet call over all 12 games (about 13k input / 1.2k output tokens), a few cents, written once. The coach only sees a compact view of the analysis, and the system prompt and game context are prompt-cached. Every call's token usage is logged in the `llm_usage` table, per player and task, and `USER_DAILY_TOKEN_LIMIT` caps it per player if you need to.

## Licensing

Stockfish and Stockfish.js are GPL-3.0, and the frontend serves them to users' browsers, which has GPL-3.0 implications for the frontend. The backend is kept fully separate (it never bundles or links Stockfish) so it can remain private. Get legal advice before you distribute CoChess or change that arrangement.
