# CoChess v2 handoff

For the session that starts v3. This covers what the code alone won't tell you. For the full decision log see `docs/PLAN_V2.md` §6 (deviations proposed at M0) and §7 (decisions made while building). For a milestone-by-milestone summary see `V2_COMPLETED_NOTES.md`.

## State at handoff

- **v2 is merged into `main` and tagged `v2`.**
  - Checks at the tag: backend 578 pytest tests (98% coverage), ruff and mypy strict clean; frontend 184 Vitest tests, oxlint, typecheck and build clean; Playwright 5 flows passing.
  - The branch is also named `v2`, so `git` can call `v2` ambiguous. Use `refs/tags/v2` or `refs/heads/v2` when it matters, or delete the branch.
- **Deployed:** AWS EC2 at `https://3-15-12-174.sslip.io`, running the M7 build (`d941fd2`), with Caddy in front. The owner has a login there.
- **The owner's local Docker app** (compose project `cochcess`, port 8080) still runs a pre-v2-M5 build. Its database holds duplicate uploads (10 rows, 6 distinct games). It hasn't been upgraded on purpose; ask before touching it.

## Milestones

| Milestone | State |
|---|---|
| M0 plan, v1 as-built record | Done |
| M1 users, invite links, sessions, user scoping, Alembic | Done |
| M2 analysis board, live engine | Done |
| M3 position-aware chat and Explain | Done |
| M4 critical moments | Done |
| M5 tendencies (+ duplicate-upload rejection, added at the M5 checkpoint) | Done |
| M6 onboarding and baseline report | Done, except removing a game from onboarding once it's added (not built) |
| M7 E2E flows, token limit, docs, deploy | Done |

**Still open from SPEC_V2's done condition:** the owner hasn't yet stepped through the critical moments of 5 of their own games on the deployed app.

## Where the build differs from or goes beyond SPEC_V2

The owner approved these at the checkpoints. The reasoning is in PLAN_V2 §6–§7.

- **Withholding goes further than the spec.**
  - Moment calls are single-turn and get their own context: the PGN up to the moment, no synopsis, no chat history.
  - Before a moment is solved or revealed, the payload leaves out every move that would grade "good" or better, not just the best move. Engine lines are cut just before such a move rather than dropped.
  - The leak check matches by move number, so the same SAN on another turn isn't a false leak.
  - Why: v1's cached game context, the stored synopsis and chat history all contained the answers.
- **During an active moment** free chat, Explain and the engine panel are disabled. Leaving the Moments tab pauses the moment.
- **The synopsis is collapsed behind a spoiler note** on games with unsolved moments, because it names the better moves.
- **Game status** is `uploaded → scanned → analyzed`. Verify and summary happen together, so the spec's separate "verified" and "summarized" states would always change at the same time.
- **Elo and playstyle:** `games.elo` is the Elo at analysis. The coach uses the *current* profile for chat, Explain and moments; the synopsis uses the game's stored Elo.
- **`games.user_id` is nullable.** A migration can't know the owner; `cli assign-games` fills it. Every query filters on `user_id`, so unassigned games are invisible.
- **The daily game cap applies per player**, not to the whole server. Onboarding games don't count against it; a player can add at most 12 onboarding games.
- **Duplicate uploads are rejected** with 409, which the spec doesn't mention; the owner asked for it.
  - The fingerprint is players, result and moves. Dates are left out because Chess.com's API export adds UTCDate/UTCTime, and color is left out too.
  - The column isn't unique, because older databases already hold duplicates.
- **Tendency ranking:** each fact counts with its own severity weight. Game-level `note` facts never count, because v1 always emits `pawn_structure` and `time_trouble` notes.
- **Onboarding:** correspondence games are a "wrong time control". The slot preview comes from the server (`POST /parse` with per-game choices), so the slot rules live in one place.
- **Baseline report:** the backend counts the openings (`opening_groups`), because the model miscounted results on the first real run. `GET /api/onboarding/report` is an addition to SPEC_V2 §11.
- **Invite tokens** are sent in the URL fragment (`/redeem#token=…`) so they never reach logs or `Referer` headers. `PUBLIC_BASE_URL` builds the link.
- **Dependencies:** `@lichess-org/chessground` replaces the deprecated `chessground` (GPL-3); `chess.js` was added. Nothing else was added.
- **Promotion on the board is always to a queen.** There's no piece picker.

## User feedback so far

- **White was pre-selected as the color, so games were analyzed from the wrong side.** This is the top v3 fix (SPEC_V3 §4.6, M1).
  - Single upload: `frontend/src/components/GameInput.tsx` starts with `useState<Color>('white')`.
  - Onboarding: each row is pre-filled with the color suggested from the player name (`ParsedRow.user_color` falls back to `suggested_color`), and `PasteGames.tsx` falls back to `'white'` on submit. The server only fills a slot for a row with a color, so that fallback normally isn't reached.
  - The backend already requires `user_color` with no default on `POST /api/games` and onboarding `submit`. Only the frontend pre-selects.
  - **Fixing an existing wrong-side game is harder than it looks:**
    - There's no endpoint or UI to change a game's color or delete a game.
    - The duplicate check ignores color, so re-uploading the same game as the other side gets 409.
    - Today the owner can only fix it by hand in SQLite.
    - v3 needs a way out, for example a "change color" action that rebuilds the summary from stored engine results (as `cli backfill` does), or a delete action.
- **"The report looks good"**: the owner approved the baseline report (512 words, 0 invalid moves) at M6.
- **Reject duplicate uploads** (owner, at the M5 checkpoint). Their database already held copies of the same games.
- **Whole engine lines were being removed** from moment payloads (owner's games, M4 checkpoint). Lines are now cut at the withheld move instead.
- **"It says I have been logged out"**: a used or expired link shows the logged-out page. The fix is a new link (`cli invite`). The owner then asked how to make links themselves; the CLI is in CLAUDE.md and DEPLOY.md.
- **New to AWS, no domain:** DEPLOY.md was rewritten as a step-by-step EC2 guide using sslip.io.

## Known bugs, rough edges, TODOs

- **The color default** and the **missing way to fix a wrong-side game**: see above.
- **There's no way to delete a game**, and none to remove one from onboarding.
- **The owner's local database has duplicate games.** `cli backfill` lists them but deletes nothing.
- **Optional `NOT NULL` migration:** once every game is assigned, `games.user_id` could be made `NOT NULL`. Not done.
- **Build warnings, harmless so far:**
  - The Vite build warns about a large chunk; no code splitting yet.
  - Vitest suggests a jsdom pool setting for speed.
- **sslip.io:** many people share it, so Let's Encrypt sometimes rate-limits it (Caddy falls back to ZeroSSL). When a domain is bought, change the Caddyfile and `PUBLIC_BASE_URL`, then send new links.
- **Server backups are manual** (DEPLOY.md "Day-to-day"). Nothing is scheduled.
- **The local scratch dev servers** from the M6 checkpoint (Vite :5173, a recording backend :8000 on a scratch DB) have stopped. Nothing depends on them.

## Gotchas

**Hooks:**
- **Fact-Forcing Gate hook:** it blocks the first Write of each new file and many Bash calls until you state facts: the callers, that nothing duplicates the file, the data shape, and the user's current instruction quoted verbatim. State them and retry.
- **A plugin hook** reads `sed -n` in the same command as `git commit` as `--no-verify` and blocks it. Run commits on their own.

**Backend:**
- **ruff RUF003** rejects `×` and `–` in comments; use ASCII.
- **pydantic-settings nested env:** a partial override like `ENGINE__VERIFY__MIN_TIME_MS=…` crashes, because `EngineTier` fields have no defaults. Override whole tiers in code (`backend/tests/e2e_app.py::make()` does).
- **AnthropicCoachClient takes the API key, not `Settings`.** Passing `Settings` gives a 401.

**Frontend:**
- **oxlint fails on warnings** and flags `set-state-in-effect`. Derive state or use handlers instead.

**E2E:**
- **`npm run e2e:real` overwrites `backend/tests/fixtures/engine/<game>.json`.** Run `git restore` on it afterwards unless you meant to re-capture.
- **Playwright strict mode:** text such as "3. Ng5" appears in several places. Scope locators to a list or region.
- **The scripted E2E coach** reads the task from the latest user message only. The history contains older tasks.
- **The scripted engine** detects mate from the SAN `#`. Generating moves for that made it too slow.

**Chess.com exports:**
- The API's PGN adds `UTCDate`/`UTCTime`; the site download doesn't. This is why dates aren't in the fingerprint.
- Public games: `https://api.chess.com/pub/player/<user>/games/archives`. The owner is `nander100` and plays 10-minute rapid.

**Deploy:**
- Set `COCHESS_PORT=127.0.0.1:8080` in the compose `.env`, or the app binds to every interface.
- Run `sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` before reloading. A bad site address ("cannot contain a comma") makes the reload fail, and Caddy keeps serving its welcome page.
- Manage Caddy only with `systemctl`. `caddy start` fails with "address already in use" on port 2019, because the service is already running.
- `PUBLIC_BASE_URL` must be the exact https hostname, or the login links are wrong.
