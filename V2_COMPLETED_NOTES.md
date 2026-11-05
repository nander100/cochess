# CoChess v2: completed work

A handoff record for future sessions. It summarizes what v2 built, what was decided along the way, and the state things were left in. For detail, follow the pointers. The code wins over this file if they disagree.

- Spec: `SPEC_V2.md`. Workflow: `PROMPT_V2.md`. Plan and every decision made while building: `docs/PLAN_V2.md` (§7 is the decision log).
- What v1 became: `docs/v1-as-built.md`. Commands and conventions: `CLAUDE.md`. Deploying: `docs/DEPLOY.md`.
- Next up: v3 (`SPEC_V3.md`, `PROMPT_V3.md`, `CLAUDE_3.md`, untracked when this was written).

## Status

- **All v2 milestones M0–M7 are done and approved by the owner** at their checkpoints.
- **Git:** `main` and `v2` both point at `d941fd2`, which is pushed to GitHub (`nander100/cochess`). `main` was fast-forwarded to `v2`; there's no merge commit. Push only when the owner asks.
- **Checks at the end of M7:**
  - backend: 578 pytest tests, plus ruff and mypy strict;
  - frontend: 184 Vitest tests, plus oxlint, typecheck and build;
  - Playwright: 5 E2E flows, about 40 s.
  - All passed.
- **Deployed** on AWS EC2 (Ubuntu 24.04, t3.small, Elastic IP) at `https://3-15-12-174.sslip.io`.
  - There's no domain yet: sslip.io supplies the hostname, and Caddy gets the TLS certificate and proxies to the Docker stack on `127.0.0.1:8080`.
  - The owner has a working login there.
- **Still open from the spec's v2 done condition:** the owner stepping through critical moments on 5 of their own games.

## Milestones

### M0: groundwork
- Wrote `docs/v1-as-built.md`, `docs/PLAN_V2.md`, and a v2 version of `CLAUDE.md`.

### M1: players and logins
- **Migrations:** Alembic in batch mode with named constraints. 0001 is the v1 baseline. The app runs migrations itself at startup.
- **Users and logins:** users, invite links and sessions (0002).
  - Only hashes of tokens are stored.
  - Links work once and expire after 7 days; sessions last 30 days.
  - Cookies are httpOnly, SameSite=Lax, and Secure in production.
- **User scoping (0003):** every route sits behind a login, and every query is scoped by `user_id`. Another player's data returns 404.
- **Owner CLI** (`app/cli.py`): `create-user`, `invite` (prints `PUBLIC_BASE_URL/redeem#token=…`), `assign-games`, and `backfill`, added in later milestones.
- **Frontend:** the profile page and the redeem page.

### M2: analysis board
- **Board:** chessground with a game tree, move list, eval graph and eval bar.
- **Pages:** My games and Analysis.
- **Live engine panel:** the `engine.live` tier, MultiPV 3. Live results are only shown, never stored.
- **Small rules:** promotion is always to a queen; PGN dates are shown as UTC.

### M3: position-aware chat and Explain
- **Path replay** (`analysis/paths.py`): the client sends UCI paths, and the backend replays them to get FEN, SAN and PGN.
- **Engine results by position** (0004): `position_key` is an indexed lookup column. Results for a position not yet analyzed come from the browser and are checked against the replayed position. If there's none, the request gets 409.
- **Explain** reuses the chat's system prompt so the cached prefix is shared. Caching uses three breakpoints: system, game context, and history.

### M4: critical moments
- **Engine side:** moment selection, grading, banned moves, attempt detectors and hints (`analysis/moments.py`).
- **Exercise flow** (`coach/moments.py`, 0005 `moment_progress`), with routes for start, attempt, ask, reveal and wrap_up.
- **"Withhold, don't instruct":**
  - Before a moment is solved or revealed, its best move and every move that would grade "good" or better are left out of the payload. Engine lines are cut just before the first such move.
  - The leak check matches moves by move number. On a leak it regenerates once, then strips the move and logs `moment_leak`.
- **Frontend:** a stepper on the board that locks the board during a moment.

### M5: tendencies
- **Math** (`analysis/tendencies.py`, pure functions, tests with hand-computed values):
  - Each game's weight is `0.5^(age/10)`.
  - Severity weights: blunder 3, mistake 2, inaccuracy 1, game-level concern 2, note 0.
  - Themes are ranked by weighted severity.
  - The trend compares ages 0–4 with 5–9 (margin 0.25) and is null under 10 games. Tendencies are provisional under 5 games.
- **Storage** (0006): theme facts per game, and a snapshot after each analyzed game. `GET /api/tendencies`.
- **The coach's player payload:** the top 5 tendencies without scores, plus accuracy by phase and by color, in every coach task.
- **Owner tool:** `scripts/print_tendencies.py` prints the math.
- **Duplicate uploads are rejected** (0007 `games.fingerprint`). The fingerprint is a sha256 of White, Black, Result and the UCI moves.
  - Dates and times are excluded, because Chess.com's API export adds UTCDate/UTCTime.
  - A second upload by the same player gets 409.
  - `cli backfill` recomputes fingerprints and lists duplicates without deleting them.

### M6: onboarding and the baseline report
- **Slots** (`analysis/onboarding.py`): 12 slots, 3 each of white_win, white_loss, black_win and black_loss, all in the primary time control.
  - Categories use Lichess's thresholds on base + 40 × increment: bullet under 180 s, blitz under 480 s, rapid under 1500 s, otherwise classical. An `N/M` header means correspondence.
  - Every game that fills no slot gets a reason.
  - A color is suggested from the name in more than half the pasted games.
- **Endpoints** `/api/onboarding/`: `parse`, `submit`, `status`, and `report` (GET; POST as SSE). The server decides the slots. Only games that fill a slot are stored, with `source = onboarding`.
- **Baseline report** (`coach/baseline.py`, prompt `baseline_report.md`, 0008):
  - One synopsis-model call at medium effort.
  - Openings are counted in the backend (`opening_groups`), because the model miscounted them.
  - The report is stored, and asking again for the same games replays it.
- **Frontend:** `/onboarding` ("Assessment" in the nav) with a paste-and-check table, slot checklist, analysis queue (`analysis/queue.ts`, resumes from the server's status) and report panel. Players land there after their first profile save.
- **Checkpoint evidence:** 12 real games (5 fixtures plus 7 from Chess.com, user nander100) filled every slot through the UI with real Stockfish. The report was 512 words with 0 invalid moves, and the owner approved it.

### M7: harden and ship
- **E2E:**
  - Under `E2E_FAKE_ENGINE=1`, the `@engine-transport` Vite alias swaps in a scripted engine (`src/test/scriptedEngine.ts`).
  - A scripted coach lives in `backend/tests/e2e_app.py`.
  - The flows are in `frontend/e2e/flows/` (coaching, onboarding, errors). They caught two real UI bugs, now fixed.
  - `npm run e2e:real` runs v1's real-Stockfish spec. It **overwrites `backend/tests/fixtures/engine/<game>.json`**; restore that file with `git restore`.
- **Optional per-player daily token cap** `USER_DAILY_TOKEN_LIMIT` (off by default). Over the cap, the coach, moments and baseline-report routes answer 429.
- **Docs:** README, CLAUDE.md, and DEPLOY.md, rewritten for a first AWS deploy without a domain.

## Deploy notes (lessons from the first real deploy)

- **Port:** on the server, `~/cochess/.env` must say `COCHESS_PORT=127.0.0.1:8080`. Without it the frontend binds to `0.0.0.0:8080`. The security group blocks that port, but it's still exposed on the host.
- **Caddyfile:**
  - It must hold only the site block, named after the real hostname: Elastic IP with dashes, then `.sslip.io`.
  - A malformed address ("Site addresses cannot contain a comma") makes `reload` fail, and Caddy keeps serving its default welcome page.
  - Check with `sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`.
  - Manage Caddy only through `systemctl`; `caddy start` fails because the service already holds port 2019.
- **`PUBLIC_BASE_URL`** in `backend/.env` must be the https hostname, or login links point to the wrong place.
- **Players:** `docker compose exec backend uv run --no-dev python -m app.cli create-user --name "…"`, then `invite --user "…"`.

## Rules that stay in force

- The engine analyzes; the LLM explains and never names a move missing from its payload. The backend validates every move the coach mentions.
- Secrets stay out of the payload; the leak check is only a backstop.
- Never trust the client for chess facts or identity. Engine results are checked and never shared across users.
- Never commit or print `.env`, API keys, the SQLite database, or invite links. The Anthropic key is backend-only.
- Commit after each working step, and stop at each ✅ checkpoint with evidence. Ask before adding dependencies or changing approved schemas.
- Don't touch the owner's local Docker app (compose project `cochcess` on :8080) or the server without asking.

## Tooling quirks seen in this repo

- A "Fact-Forcing Gate" hook blocks the first Write of each new file and some Bash calls. Retry after stating the facts it asks for, including the user's instruction quoted verbatim.
- A plugin hook falsely flags `sed -n` in the same command as `git commit` as "--no-verify", so run commits on their own.
- ruff's RUF003 rejects `×` and `–` in comments; use ASCII.
- pydantic-settings: a partial nested env override such as `ENGINE__…` crashes for `EngineTier`, whose fields have no defaults. Set tiers in code; `e2e_app.make()` does this.
