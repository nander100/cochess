# CoChess

An AI chess coach for intermediate players (roughly 1000–1800 Elo). Paste a game in PGN; Stockfish analyzes every move in your browser, rule-based detectors work out what *kind* of mistakes you made, and a Claude-powered coach explains it all in plain, encouraging language. Then ask follow-up questions, including "what if I had played X?", which the engine analyzes on the spot.

**The golden rule: the engine analyzes, the coach explains.** Stockfish decides how good every move is. The coach reasons about the position, but every move it writes is checked against the engine's data before you see it, and anything it can't back up is removed.

## How it works

1. **Log in** with a one-time link from the owner, then fill in your profile: rating, the time control you play most, and (optionally) your style. Add your **Chess.com or Lichess username** and CoChess fills in the color you played in every game you paste or import.
2. **Bring in your games.** Paste a PGN (choose your color, or let your username decide), or **import your recent games** from Chess.com or Lichess: review them, tick the ones you want, and they're added and analyzed one after another. Games you already have are marked and skipped.
3. **Onboarding assessment (optional).** Paste or import 12 games in your main time control: 3 wins and 3 losses with each color. CoChess checks which slot each fills, analyzes them in your browser (closing the tab and coming back picks up where it stopped), and your coach writes a **baseline report**: strengths, the top 3 things to work on with examples, your openings, and a 2–4 week plan.
4. **Analysis.** Stockfish (WASM, multi-threaded where the browser allows) **scans** every position, then **verifies** the moments that matter with a deeper 4-line search. The backend classifies every move (Lichess winning-chances model), computes Lichess-style accuracy, and runs nine theme detectors (hung piece, allowed tactic, missed tactic, missed capture/check, king safety, pawn structure, endgame technique, slow development, time trouble).
5. **The analysis board.** Step through the game, see the eval graph and a live engine panel, and play your own variations: they're **saved**, and **Export PGN** downloads the game with your variations, the engine's evaluations, your mistakes marked and the coach's notes.
6. **Your coach** (Claude) writes a short synopsis, answers questions about the position on the board, and explains it on request, in **plain language** at the detail level you choose (Plain, Standard, Technical). It never writes out a line of moves: it links to one, and the board **plays the line** for you, stopping where the difference shows. It **draws on the board** (arrows and highlights), each one checked before it's shown, and can **walk you through** any line move by move.
7. **Critical moments.** Your biggest mistakes become exercises: find a better move yourself, get graded by the engine, get hints, then see the engine's move. The coach never sees the answer before you've found it or asked for it.
8. **Your progress.** The Games page is your dashboard: your top focus areas with an example from your games and matching **Lichess puzzle themes**, games with moments left to practice, how your mistake types and accuracy change over time, and recent games. Filter by time control, color and range.

Specs: [`SPEC_V3.md`](SPEC_V3.md) (current), [`SPEC_V2.md`](SPEC_V2.md) and [`SPEC.md`](SPEC.md). Plans and every design decision: [`docs/PLAN_V3.md`](docs/PLAN_V3.md) (and the earlier `docs/PLAN_V2.md`, `docs/PLAN.md`). What each version actually became: [`docs/v3-as-built.md`](docs/v3-as-built.md), [`docs/v2-as-built.md`](docs/v2-as-built.md). Conventions and commands for contributors: [`CLAUDE.md`](CLAUDE.md).

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
| `LIMITS__MAX_GAMES_PER_DAY` | `10` | New single games per player per rolling 24 hours, pasted or imported (onboarding games don't count). |
| `USER_DAILY_TOKEN_LIMIT` | *(off)* | Claude tokens one player may use in a rolling 24 hours; past it, coach requests are refused until the next day. |
| `COACH__CHAT_MAX_MESSAGES` | `30` | Questions per game (chat and critical moments together). |
| `COACH__SYNOPSIS_EFFORT`, `COACH__CHAT_EFFORT` | `low`, `medium` | Claude effort level (`low` … `max`): trades depth for speed and cost. |
| `THRESHOLDS__INACCURACY` / `__MISTAKE` / `__BLUNDER` | `0.10` / `0.20` / `0.30` | Winning-chances drop for each label. |
| `IMPORTS__APP_NAME`, `IMPORTS__CONTACT` | `CoChess`, *(none)* | How game import names itself to Lichess and Chess.com (User-Agent `CoChess (contact)`). Chess.com asks API clients for a contact, such as an email; set one in production. |
| `IMPORTS__DEFAULT_GAMES` / `__MAX_GAMES` / `__COOLDOWN_SECONDS` | `20` / `50` / `10` | Games fetched per import by default, the most one import fetches, and the wait between a player's imports. |
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

`npm run e2e` (from `frontend/`) drives the real backend and frontend in your installed Chrome, with a **scripted engine** (real chess rules, material-only evaluation) and a **scripted coach**: free, the same every run, about two minutes. Chess.com and Lichess are faked too. It covers login → upload → board → synopsis, chat and Explain → a critical moment; color selection (none pre-selected; detection from a username); changing a game's color and deleting it; coach drawings, line walkthroughs and line playback; saved variations, PGN export and re-import; the dashboard; importing from Chess.com and Lichess; onboarding through the baseline report (with a reload mid-analysis); the error states (used login link, illegal or non-standard PGN, duplicate upload, another player's game); and screenshots of every page in both themes.

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
uv run python -m scripts.seed_owner_games --db /tmp/demo.db # owner games, analyzed, on a scratch database (prints a login link)
uv run python -m scripts.print_summary game1w --compact   # the summary the coach sees
uv run python -m scripts.synopsis game5b --elo 1400       # a real synopsis (calls the API)
uv run python -m scripts.print_tendencies --user "Alex"   # tendencies with the math shown
```

## Cost

With the default models, a game costs about **$0.02**: the synopsis (Claude Sonnet 5.5 at low effort, about 4.7k input / 0.7k output tokens) plus well under a cent per chat question or critical-moment step (Claude Haiku 5.5). The baseline report is one Sonnet call over all 12 games (about 13k input / 1.2k output tokens), a few cents, written once. A line walkthrough is one Haiku call (about 3k input / 0.9k output tokens) and is cached per player and line, so walking the same line again is free; at most 30 new walkthroughs per game. A reply that fails the move or drawing checks is regenerated once, which can double that reply's cost. The coach only sees a compact view of the analysis, and the system prompt and game context are prompt-cached. Every call's token usage is logged in the `llm_usage` table, per player and task, and `USER_DAILY_TOKEN_LIMIT` caps it per player if you need to.

## Licensing

Stockfish and Stockfish.js are GPL-3.0, and the frontend serves them to users' browsers, which has GPL-3.0 implications for the frontend. The backend is kept fully separate (it never bundles or links Stockfish) so it can remain private. Get legal advice before you distribute CoChess or change that arrangement.
