# CoChess

An AI chess coach for intermediate players (roughly 1000–1800 Elo). Paste a game in PGN; Stockfish analyzes every move in your browser, rule-based detectors work out what *kind* of mistakes you made, and a Claude-powered coach explains it all in plain, encouraging language. Then ask follow-up questions, including "what if I had played X?", which the engine analyzes on the spot.

**The golden rule: the engine analyzes, the coach explains.** Stockfish decides how good every move is. The coach reasons about the position, but every move it writes is checked against the engine's data before you see it, and anything it can't back up is removed.

## How it works

1. You enter your rating, the color you played, an optional description of your style, and the PGN.
2. The backend validates the game (python-chess) and returns every position.
3. Stockfish (WASM, multi-threaded where the browser allows) **scans** every position, then **verifies** the moments that matter with a deeper, 4-line search.
4. The backend classifies every move (Lichess winning-chances model), computes Lichess-style accuracy, and runs nine theme detectors: hung piece, allowed tactic, missed tactic, missed capture/check, king safety, pawn structure, endgame technique, slow development, and time trouble.
5. The coach (Claude Sonnet) writes a short synopsis from that data. Every move it mentions is validated before it's shown.
6. In the chat (Claude Haiku) you can ask anything about the game. When you ask about a move the analysis doesn't cover, the coach asks your browser's engine for a **deep-dive** and answers from the result.

Full product spec: [`SPEC.md`](SPEC.md). Implementation plan and every design decision: [`docs/PLAN.md`](docs/PLAN.md). Conventions and commands for contributors: [`CLAUDE.md`](CLAUDE.md).

## Quick start (Docker)

You need Docker with Compose and an [Anthropic API key](https://platform.claude.com/).

```bash
cp backend/.env.example backend/.env
# Edit backend/.env: set ACCESS_CODE to a long random string and ANTHROPIC_API_KEY to your key.
docker compose up --build
```

Open <http://localhost:8080>, enter the access code, and paste a game.

To put it on a server for your testers, follow [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Configuration

Settings come from `backend/.env` (never commit it). Nested settings use `__`.

| Variable | Default | What it does |
|---|---|---|
| `ACCESS_CODE` | *(empty)* | Shared code testers enter once per browser session. **Empty turns the gate off**, which is only for local development; the backend logs a warning. |
| `ANTHROPIC_API_KEY` | *(empty)* | Needed for the coach. Without it, analysis still works and the coach panel says it isn't set up. |
| `COACH_MODEL_SYNOPSIS` | `claude-sonnet-5-5` | Model for the synopsis (low effort). `claude-opus-5-5` writes deeper synopses at about 2× the cost. |
| `COACH_MODEL_CHAT` | `claude-haiku-5-5` | Model for the chat. `claude-sonnet-5-5` reasons more carefully at about 20× the cost per message. |
| `DATABASE_URL` | `sqlite:///./cochess.db` | Docker overrides it to a file on the `cochess-data` volume. |
| `LIMITS__MAX_GAMES_PER_DAY` | `10` | New games per rolling 24 hours, for the whole server. |
| `COACH__CHAT_MAX_MESSAGES` | `30` | Questions per game. |
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

`npm run e2e` (from `frontend/`) drives the real stack in your installed Chrome: it starts the backend and Vite, pastes one of the owner's games, and runs Stockfish for real (about 40–90 seconds). The coach is **off** by default because it calls the paid API.

```bash
npm run e2e                                         # engine only, free
E2E_GAME=game3w.txt npm run e2e                     # another game
E2E_COACH=1 npm run e2e                             # + a real synopsis (~$0.05)
E2E_COACH=1 E2E_QUESTIONS="What if I had played 31...Kf7?" npm run e2e   # + chat
E2E_BASE_URL=http://localhost:8080 E2E_ACCESS_CODE=... npm run e2e   # against docker compose
```

Evidence (depth/time per search, the synopsis, the chat transcript) is written to `frontend/test-results/`.

Two scripts help when tuning the analysis on real games (from `backend/`):

```bash
uv run python -m scripts.print_summary game1w --compact   # the summary the coach sees
uv run python -m scripts.synopsis game5b --elo 1400       # a real synopsis (calls the API)
```

## Cost

With the default models, a game costs about **$0.02**: the synopsis (Claude Sonnet 5.5 at low effort, about 4.7k input / 0.7k output tokens, ~$0.018) plus well under a cent per chat question (Claude Haiku 5.5). The coach only sees a compact view of the analysis (an annotated move list and trimmed engine lines), and the system prompt and game context are prompt-cached. Every call's token usage is logged in the `llm_usage` table, and `uv run python -m scripts.synopsis game5b --elo 1400 --model claude-haiku-5-5` estimates the cost of a synopsis for any model.

## Licensing

Stockfish and Stockfish.js are GPL-3.0, and the frontend serves them to users' browsers, which has GPL-3.0 implications for the frontend. The backend is kept fully separate (it never bundles or links Stockfish) so it can remain private. Get legal advice before you distribute CoChess or change that arrangement.
