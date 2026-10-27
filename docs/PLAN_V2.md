# CoChess v2 — Implementation Plan (M0)

Status: **approved 2026-10-26.** The owner approved the dependencies in §6 Q1 and every recommendation in §6 as written. Q15 (deployed v1 data) wasn't answered: `assign-games` is built and tested either way. Sources: `SPEC_V2.md` §1–§13, `docs/v1-as-built.md`, the code at tag `v1`.

---

## 0. Verified facts (checked 2026-10-26)

| Item | Finding | Source |
|---|---|---|
| chessground | The `chessground` npm package is **deprecated** ("no longer supported"). The current package is **`@lichess-org/chessground` 10.5.0**, GPL-3.0-or-later. API: `Chessground(el, config) → Api`; `api.set(config)`, `api.move`, `api.setAutoShapes`, `api.destroy()`. `Config`: `fen`, `orientation`, `turnColor`, `lastMove: Key[]`, `check`, `viewOnly`, `movable {free, color, dests: Map<Key, Key[]>, showDests, events.after(orig, dest, meta)}`. CSS ships in `assets/` (`chessground.base.css`, `.brown.css`, `.cburnett.css`). | npm registry, the package's `.d.ts` files |
| chess.js | **1.4.0**, BSD-2. `new Chess(fen?)`, `move("Nf3" \| {from, to, promotion})` **throws** on an illegal move (it does not return null); `Move` has `san`, `lan`, `before`, `after`, `from`, `to`, `promotion`, `isCapture()`, …; `moves({square, verbose: true})`, `fen()`, `inCheck()`, `isGameOver()`. | the package's `dist/types/chess.d.ts` and ESM source |
| Lichess time controls | Estimated duration = `limitSeconds + 40 * incrementSeconds` (`Clock.Config.estimateTotalSeconds`). Speed ranges: UltraBullet 0–29, Bullet 30–179, Blitz 180–479, Rapid 480–1499, **Classical 1500–21599, Correspondence ≥ 21600**. This matches SPEC_V2 §10.2, except the spec has no correspondence category. | `scalachess` `Clock.scala`, `Speed.scala` |
| Alembic + SQLite | Alembic **1.20.1**. SQLite needs "move and copy" for anything but `add_column`: use `op.batch_alter_table()`, and set `render_as_batch=True` in `env.py` for autogenerate. Unnamed constraints can't be dropped, so give `MetaData` a **`naming_convention`**. Disable `PRAGMA foreign_keys` during batch ops on tables that others reference. Unnamed CHECK constraints are lost on recreate. | alembic.sqlalchemy.org/en/latest/batch.html |
| Prompt caching | **Up to 4 `cache_control` breakpoints** per request. The prefix order is `tools` → `system` → `messages`, and a change invalidates its level and everything after it. Each breakpoint writes its own entry; reads look back up to 20 blocks. The minimum is 512 tokens for Sonnet/Haiku/Opus 5.5. TTL is 5 min by default, or `"ttl": "1h"` (1h entries must come before 5m entries). Syntax: `{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}` on each block to cache. | platform.claude.com prompt-caching |

---

## 1. Architecture changes at a glance

```
Browser                                         Backend
───────                                         ───────
/redeem#token=…  ── POST /api/auth/redeem ────► invites → sessions (cookie)
Games page       ── GET  /api/games ──────────► user-scoped list
Analysis page    ── GET  /api/games/{id} ─────► positions, win% curve, labels, stored
                                                engine results, moments + progress,
                                                synopsis, chat history (display form)
  game tree (chess.js) → path_uci
  Explain / Chat ── {path_uci, engine_result?}► paths.replay(path) → FEN/SAN/PGN
                                                engine_result checked vs replayed FEN
                                                payload v2 → Claude (cached system +
                                                game context) → validate → SSE
  Moments        ── start / attempt / reveal ─► moments: grade, hints, withhold,
                                                leak check → SSE (meta, text, done)
Onboarding page  ── parse / submit / status ──► split PGNs, slots, queue status
  queue runner: scan + verify per game (resumable from server status)
                                                summary → theme facts → tendencies
                                                → snapshot
```

All auth goes through one dependency, `get_current_user`. Everything below it receives a `User` and scopes every query by `user_id`.

---

## 2. Data model and migrations

### 2.1 Alembic setup (M1, step 1)

- `backend/alembic/` with `env.py` reading `DATABASE_URL` from `Settings`, `render_as_batch=True`, `target_metadata = Base.metadata`.
- `Base.metadata` gets a `naming_convention` (ix/uq/ck/fk/pk), so every constraint has a name from now on.
- **`0001_v1_baseline`**: written by hand to match `create_all` at tag `v1` exactly (six tables, the same unique constraint).
- **Startup / deploy**: `app.db.migrate.upgrade(engine)` runs in the Docker entrypoint before uvicorn. If the DB has v1 tables and no `alembic_version`, it stamps `0001` first, then upgrades. `create_app` no longer calls `create_all`; tests build schema with `alembic upgrade head` on in-memory SQLite. A test asserts the migrations produce exactly `Base.metadata`, using `alembic.autogenerate.compare_metadata`.
- Data backfills (theme facts, engine-result position keys) are **CLI commands, not migrations**, so migrations never import app code that later changes. Migrations only change schema.

### 2.2 v2 schema

New tables:

| Table | Columns | Constraints / indexes |
|---|---|---|
| `users` | `id` str UUID PK, `name` (≤ 60), `elo` int null, `time_control` (`bullet`/`blitz`/`rapid`/`classical`) null, `playstyle` (≤ 500) null, `created_at`, `updated_at` | `uq(name)` case-insensitive (`COLLATE NOCASE`), because the CLI looks users up by name |
| `invites` | `id` int PK, `user_id` FK, `token_hash` (sha256 hex), `expires_at`, `used_at` null, `created_at` | `uq(token_hash)` |
| `sessions` | `id` int PK, `user_id` FK, `token_hash`, `expires_at`, `created_at` | `uq(token_hash)`; logout deletes the row |
| `game_theme_facts` | `id`, `user_id` FK, `game_id` FK, `theme`, `subtype` null, `ply` null, `move_number` null, `move_san` null, `severity`, `phase` null, `user_color`, `details` JSON | `ix(user_id, theme)`, `ix(game_id)`; rebuilt per game on every summary build |
| `tendency_snapshots` | `id`, `user_id` FK, `games_analyzed`, `report` JSON (the full `TendencyReport`), `created_at` | `ix(user_id, created_at)` |
| `moment_progress` | `id`, `user_id` FK, `game_id` FK, `moment_index`, `state` (`intro`/`attempt`/`solved`/`revealed`), `attempts` JSON (`[{candidate_uci, san, grade, reasoning, eval_after}]`), `revealed` bool, `updated_at` | `uq(game_id, moment_index)` |
| `baseline_reports` | `id`, `user_id` FK, `text`, `invalid_moves_removed` JSON, `game_ids` JSON, `created_at` | latest one shown |

Changed tables. All are adds, except the one batch recreate for `engine_results`:

| Table | Change |
|---|---|
| `games` | `+user_id` FK **nullable** (§6 Q6), `+time_control_category` null, `+user_result` (`win`/`loss`/`draw`) null, `+played_at` datetime null (from `UTCDate`/`UTCTime`, then `Date`, then `created_at`), `+status` (§6 Q7) default `uploaded`, `+source` (`single`/`onboarding`) default `single`, `ix(user_id, played_at)`. **`elo` is kept as the Elo at analysis**, not renamed (§6 Q5). |
| `engine_results` | `+user_id` FK null, `+position_key` (the first four FEN fields: placement, side, castling, en passant), unique becomes `uq(game_id, position_key, tier)` (batch recreate). The CLI `backfill` sets `position_key` and `user_id` on v1 rows. |
| `chat_messages` | `+path_uci` JSON null. `content.type` gains `"explain"` and `"moment"`. Each chat row's content also stores `display` (the player's plain message), so history can be shown without parsing the payload (no column change). |
| `pending_tool_calls` | `+path_uci` JSON null: the board position the message was sent from, needed because `ply` is now optional (§6.2). **This column is not in SPEC §12.** |
| `llm_usage` | `+user_id` FK null, `+task` (`synopsis`/`chat`/`explain`/`moment_intro`/`moment_feedback`/`baseline_report`) |

`GameSummary` JSON gains `moments: list[Moment]` (§8.1, stored with the summary as the spec says) and per-move `phase` in `move_list` (needed for the theme-fact `phase` column and the eval graph). These are model changes inside the JSON, not schema.

### 2.3 Migration list

`0001_v1_baseline` → `0002_users_auth` (users, invites, sessions) → `0003_user_scoping` (games, engine_results.user_id, llm_usage) → M3: `engine_results.position_key` + `chat_messages.path_uci` + `pending_tool_calls.path_uci` → M4/M5: game_theme_facts, tendency_snapshots, moment_progress → M6: baseline_reports. Each one lands with the milestone that needs it (changed at M1: the M3 columns moved out of `0003`, so nothing is added before it's used).

---

## 3. Backend modules and interfaces

```python
# app/auth/  (M1) — the only module that knows about invites/cookies; v4 swaps it for OAuth
tokens.py      new_token() -> str (secrets.token_urlsafe(32)); hash_token(t) -> str (sha256)
service.py     create_user(s, name) -> User; create_invite(s, user, now) -> str (raw token)
               redeem(s, token, now) -> SessionToken   # raises InviteInvalid (used/expired/unknown)
               session_user(s, raw_token, now) -> User | None ; end_session(s, raw_token)
deps.py        get_current_user(request, session) -> User   # 401 if no or expired session
               CurrentUser = Annotated[User, Depends(get_current_user)]
routes.py      POST /api/auth/redeem, POST /api/auth/logout ; GET/PATCH /api/me

# app/cli.py  (M1, M5) — argparse; uses the same services
create-user --name ; invite --user [--base-url] ; assign-games --user ; backfill [--user]

# app/db/games.py  (M1) — every accessor takes user_id; "not yours" == "not found"
get_game(s, user_id, game_id) -> Game   # raises GameNotFound → 404
list_games(s, user_id) -> list[GameListItem]

# app/analysis/paths.py  (M3)
class ResolvedPath(BaseModel): path_uci, path_san, fen, ply, on_mainline, branch_ply,
                               variation_san, pgn_to_move
resolve_path(game: ParsedGame, path_uci: list[str], max_plies) -> ResolvedPath  # PathError on illegal/bad UCI
position_key(fen) -> str

# app/analysis/engine.py  (M3) — add, reusing _check_result
check_for_position(result, *, expected_fen, tier, tier_config) -> EngineResult
    # position_key(result.fen) must equal position_key(expected_fen); legality as v1

# app/analysis/moments.py  (M4) — pure
select_moments(context: GameContext, cfg) -> list[Moment]            # SPEC_V2 §8.1
grade(before: EngineResult, after: EngineResult | Evaluation, candidate, mover, cfg) -> Grade
good_first_moves(before: EngineResult, mover, cfg) -> set[str]       # the leak check's banned set
candidate_context(board, move, before, after, cfg) -> MoveContext    # so v1 detectors run on it
build_hints(candidate_facts, best_move, board) -> list[Hint]         # whitelisted fields only (§6 Q2)
class MomentState: transition(event) -> MomentState                  # intro→attempt→solved|revealed

# app/analysis/tendencies.py  (M5) — pure, hand-checked math
aggregate(games: list[GameFacts], cfg) -> TendencyReport   # weights, rates, trend, accuracy by phase/color

# app/analysis/onboarding.py  (M6) — pure
split_games(text, limits) -> list[ParsedGame | PgnError]
time_control_category(header: str | None) -> Category | None
assign_slots(existing, candidates, primary_tc) -> list[SlotDecision]  # fills or gives a reason

# app/coach/  (M3–M6)
payload.py     CoachPayloadV2 (SPEC_V2 §6.1 field for field), PositionPayload, MomentPayload,
               build_*_payload(...) per task ; context_block(summary, strip=MomentStrip | None)
prompts/       coach_system.md + synopsis.md, chat.md, explain.md, moment.md, baseline_report.md
client.py      system_blocks(task, game_context) -> 2 breakpoints (§6 Q11)
answer.py      validated_answer(client, request, allowed, banned=set()) -> Answer
               # one regenerate-then-strip loop shared by every task (extracted from
               # service.py and chat.py); banned moves → leak path, logs `moment_leak`
explain.py, moments.py, report.py   orchestration per task, like service.py
```

Frontend (`src/`):

```ts
board/tree.ts         GameTree: nodes {id, fen, san, uci, parent, children}; fromMainline(positions);
                      addMove(nodeId, uci) -> nodeId (chess.js validates); pathTo(nodeId) -> uci[]
board/Board.tsx       chessground wrapper: props {fen, orientation, lastMove, dests, onMove, viewOnly}
board/MoveList.tsx    mainline + inline indented variations, glyphs, click → select
board/EvalGraph.tsx   plain SVG, win% per ply, dots on user errors, hover eval, click → jump
board/useArrowKeys.ts ← / → over the current line
engine/search.ts      + AbortSignal (sends `stop`, resolves partial) + onInfo callback
engine/live.ts        LiveAnalysis: go infinite, MultiPV 3, stop on position change or after 10 s
engine/queue          live analysis yields to queued tier searches (cancel, then resume)
moments/Stepper.tsx   intro → attempt (board move + reasoning) → feedback → reveal → next
pages/                Redeem, Games, NewGame, Analysis, Onboarding, Profile; react-router
analysis/queue.ts     onboarding runner: reads /api/onboarding/status, scans and verifies the next
                      unfinished game, repeats; resumable because status is server-side
```

---

## 4. API additions and changes (on top of SPEC_V2 §11)

- Every route except `/api/health` and `/api/auth/redeem` depends on `CurrentUser`. The access-code middleware and `X-Access-Code` are removed.
- `GET /api/engine-config` stays (behind the session).
- `POST /api/games` body becomes `{pgn, user_color}`. Elo and playstyle come from the profile; 409 if the profile is incomplete.
- `GET /api/games/{id}` also returns `positions`, `final_fen`, per-ply `win_pct` (computed by the backend, one formula), and `verify_fens` while `status = scanned`, so analysis can resume.
- Coach SSE gains a `meta` event (attempt: `{grade, state}`). Its shape is otherwise unchanged.

---

## 5. Milestones (one commit per working step; tests alongside)

**M1 — Accounts** ✅
1. Alembic + `0001` baseline + migration-equals-models test; stamp-then-upgrade on existing DBs.
2. `0002`: users, invites, sessions; `app/auth` services with tests (expiry, single use, hashes only, 32-byte tokens, cookie flags, 30-day sessions).
3. CLI: `create-user`, `invite` (prints `{PUBLIC_BASE_URL}/redeem#token=…`), `assign-games`.
4. `0003`: user scoping; `get_current_user` on every route; `db/games.py` accessors; 404 isolation tests on **every** user-data endpoint (a parametrized test over the route table, so a new route without one fails).
5. `GET/PATCH /api/me`; per-user daily game cap (§6 Q8); access gate removed (backend + frontend).
6. Frontend: react-router, Redeem page, Profile page (first login → profile required), API client on cookies, 401 → "ask the owner for a new link".
- Evidence: auth and isolation test output, plus a walkthrough (CLI → link → redeem → profile → upload) with screenshots.

**M2 — Analysis board** ✅
1. `GET /api/games`, `GET /api/games/{id}` (positions, win%, labels, results, synopsis, chat history).
2. Upload page (v1 form minus profile fields) → runs scan/verify → opens the game page. Game `status` updates.
3. `GameTree` + tests (mainline, branching, re-entering an existing child, path round trip).
4. Chessground board, move list with glyphs and variations, arrow keys.
5. SVG eval graph.
6. `search()` cancellation + `onInfo`; live engine panel with toggle, MultiPV 3, 10 s stop, yielding to tier searches.
- Evidence: demo on a fixture game (screenshots/GIF), Vitest output.

**M3 — Position-aware chat and Explain** ✅
1. `paths.py` + tests (legal, illegal, malformed UCI, into variations, back onto the mainline, too long).
2. `check_for_position` + engine results keyed by `position_key`, user-scoped.
3. Payload v2 and `position` for chat; chat accepts `{message, path_uci, engine_result?}`; `analyze_position` v2 (`ply` optional, `candidate_moves_san` ≤ 3); pending row stores the path.
4. Frontend: verify-tier run for the current position when no stored lines exist; chat sends the path.
5. Explain endpoint, prompt, button.
6. Two cache breakpoints; usage logs `task` and `user_id`.
- Evidence: transcripts from a mainline position and from a variation, the exact payloads, cache read/write tokens on a second call.

**M4 — Critical moments** ✅
1. `select_moments` stored in the summary (rebuilt for v1 games by `backfill`).
2. Grading + `good_first_moves` + candidate `MoveContext` → detectors; hand-built FEN tests.
3. Hint builder (whitelist) + tests that no hint contains the best move, its destination square, or a field that names it.
4. Moment payloads + the stripped context (§6 Q2) + leak check (`banned` set) + `moment_leak` logging; leak tests per task.
5. `moment_progress` + start/attempt/reveal endpoints + state machine tests (2 failures → reveal, "Show me", same-as-game counts, wrap-up).
6. Moment stepper UI; engine panel, Explain, and free chat locked while a moment is unsolved (§6 Q3).
- Evidence: full walkthrough of 2 fixture games, with every payload sent before reveal printed verbatim.

**M5 — Tendencies** ✅
1. `game_theme_facts` written on every summary build; `backfill` for v1 games (phase recomputed by replaying the PGN).
2. `aggregate()` with hand-computed tests (decay, rates, severity weighting, trend, provisional).
3. Snapshot after every analyzed game; `GET /api/tendencies`; `player.tendencies` + accuracy in payloads; `recent_example` moves added to the allowed set.
- Evidence: tendency output for your games with the weights and per-theme sums printed.

**M6 — Onboarding and baseline report** ✅
1. `split_games`, `time_control_category`, `assign_slots` + tests (draws, wrong TC, full slots, missing header, correspondence).
2. parse / submit / status endpoints; the queue runner with progress and resume.
3. Baseline report payload, prompt, endpoint; stored and shown from the profile.
- Evidence: your real 12-game baseline report, plus the payload.

**M7 — Harden and ship** ✅
- Playwright with the fake engine (a Vite alias swaps the worker transport for a scripted one): login → upload → board → moment → chat; error and loading states; README, `DEPLOY.md` (migrations, backups, `PUBLIC_BASE_URL`, `Secure` cookies behind TLS).
- The v1 real-Stockfish E2E stays as an opt-in.

---

## 6. Open questions and recommended changes

Items 1–3 block M1/M2; the rest can be decided at their milestone, but I'd like your view now.

**1. New and renamed dependencies (blocking).** I need approval for:
- `@lichess-org/chessground@10.5.0` instead of `chessground`, which is deprecated on npm. It's GPL-3.0-or-later, the same license as before.
- `chess.js@1.4.0` (BSD-2).
- `react-router@7` (in the CLAUDE.md stack, so just confirming the version).
- `alembic@1.20.x` (in the stack).
- **No others.** Tests keep using `FakeTransport` and the coach fakes.

**2. Withholding has gaps the spec doesn't cover (blocking for M4).** v1's cached game context reveals the answer to every moment:
- `key_moments[].best_move_san` and `engine_lines` (whose first moves are the best moves).
- Theme-fact details `missed_tactic.best_move` and `line`, `missed_capture_or_check.best_move`, and `passive_king.best_move`.
- **The stored synopsis**, which usually names the better move.
- Chat history, which may discuss it.
- The game's later moves, where the same SAN can appear legitimately and trigger the leak check falsely.

**Recommendation: moment calls are single-turn and use their own context.** That context has:
- `pgn_to_move` truncated to the moment's ply.
- A summary with every *unrevealed* moment's best-move data removed (key-moment lines, best_move fields, theme-fact details that name moves).
- No synopsis and no chat history.
- Earlier attempts for this moment, listed in `moment.attempts`.

Hints are built from a **whitelist** of detector fields:
- Allowed: `hung_piece` piece/square/lost_to, `allowed_tactic` subtype/reply_move, `king_safety`, `pawn_structure`, `threw_win`, `allowed_passer`.
- Never allowed: `best_move`, `line`, or `passive_king`.

If the best move's SAN also appears in a line that is allowed (e.g. a refutation), that line is dropped from the payload rather than risk a false "leak".

**3. Chat and the engine during an unsolved moment (blocking for M4).** A free chat message sent from the moment's position would carry that position's engine lines, which contain the best move. **Recommendation:**
- While a moment is active (started, not solved or revealed), the chat box sends the user's text as the attempt's reasoning or as a question routed to `moment_feedback`. Free chat, Explain, and the engine panel are disabled.
- Leaving the Moments tab pauses the moment and unlocks everything. If the user peeks, it only costs them the exercise.

**4. "Mainline positions usually already have engine lines" is not true for v1 data.** Scan keeps 1 ply of PV and only about 30 of ~80 positions are verified. **Recommendation:** for chat and Explain, the browser runs the verify tier on the current position whenever no stored verify/deep result exists (1.5–3 s, "Coach is looking at the position…"), and results are cached per user and game by `position_key`.

**5. Elo and playstyle source.** The spec wants `elo_at_analysis` on games and a profile on users. v1's `games.elo` and `games.playstyle` already are per-game snapshots. **Recommendation:**
- Keep `games.elo` as the Elo at analysis (no rename) and stop asking for it on upload.
- The coach's `player` uses the **current profile** for `playstyle` and `elo`/`rating_band`, so the coach talks to who the user is now.
- The game page shows the Elo at analysis.

**6. `games.user_id` nullable.** A migration can't know the owner. **Recommendation:**
- Add it nullable; `assign-games` fills it.
- Every query requires `user_id = :me`, so unassigned games are invisible.
- After assignment you can opt into a later `NOT NULL` migration.

**7. Game `status` values.** v1 builds the summary at verify time, so "verified" and "summarized" happen together. **Recommendation:** `uploaded → scanned → analyzed` (the summary, moments, and theme facts are all built). Whether a synopsis exists is shown separately. Alternatively, keep the spec's four names with `verified` and `summarized` set atomically.

**8. The daily game cap conflicts with onboarding.** v1 allows 10 games per day for the **whole server**; onboarding needs 12 at once. **Recommendation:** `LIMITS__MAX_GAMES_PER_DAY` becomes per user (default 10), and onboarding submissions are exempt, capped at 12 accepted onboarding games per user ever. `USER_DAILY_TOKEN_LIMIT` is added as the spec says, off by default.

**9. Tendency ranking details.**
- "Rank by weighted rate × severity weight" is ambiguous when one theme has facts of mixed severity. **Recommendation:** each fact contributes its own severity weight. Score = Σ(w × Σ fact weights) / Σ(w), while `rate_per_game` stays the unweighted-severity rate.
- Game-level severities: `concern` = 2; `note` facts are **excluded** (v1 always emits `pawn_structure` and `time_trouble` notes, which would otherwise top every list).
- `pawn_structure`'s end-of-opening summary is never a tendency.
- Trend needs 10 games; with fewer it's `null`. The margin is configurable (default 0.25 per game).

**10. Correspondence / daily games.** Lichess has a correspondence category (≥ 21,600 s), and "1/259200" headers don't parse as base+increment. **Recommendation:** treat these as "wrong time control" for onboarding. They can still be analyzed as single games.

**11. Prompt caching layout.** v1 caches the system prompt and game context together, with one breakpoint. **Recommendation: up to three breakpoints.**
- One on the tools + system prompt, shared across all games for that task.
- One on the game context block.
- For chat, one on the last history message, so the conversation prefix is cached too.
- Moment calls use their stripped context, which is cached as a separate entry.
- 5-minute TTL; the 1-hour TTL isn't worth 2× writes at our volume.

**12. `analyze_position` with up to 3 plies.** **Recommendation:**
- Search the root and the final position after the sequence (2 deep searches, the same as v1), not each intermediate one.
- The tool result reports the whole sequence in SAN plus the eval after it.
- An illegal ply anywhere in the sequence returns a tool error naming it.

**13. Invite links.** **Recommendation:**
- The token goes in the URL **fragment** (`/redeem#token=…`), so it never reaches server logs or `Referer` headers.
- A new `PUBLIC_BASE_URL` setting builds the link.
- Redeem and logout are JSON-only POSTs. Together with `SameSite=Lax` this rules out cross-site form posts.

**14. Moment grading edge cases.** **Recommendation:**
- "Same as the game move" is compared by UCI, not SAN.
- A candidate that mates is `best`.
- The "best" threshold (0.02 wc) and max attempts (2) live in config.
- The wrap-up after the last moment uses `moment_feedback` with `wrap_up: true`, as the spec says.

**15. v1 data.** There's no local `cochess.db`. **Question:** is v1 deployed somewhere with games you want kept? If so, the plan is: deploy M1 → the stamp-then-upgrade migration runs → `create-user` + `assign-games --user Alex`. If not, I'll still build `assign-games` and test it, but there's nothing to migrate.

**16. Synopsis on the game page vs. moments.** The stored synopsis names better moves, so a user reading it before stepping through moments sees the answers (to the user, not the coach). **Recommendation:** collapse the synopsis by default on games with unsolved moments, with a "spoilers" note. This is cosmetic; say if you'd rather show it as v1 does.

---

## 7. Decisions made while building

**M2 (analysis board)**
- **Live engine tier** in backend config (`engine.live`: MultiPV 3, runs to its 10 s cap), served by `/api/engine-config` like the other tiers. Live results are shown only, never posted.
- **Stored engine lines carry `win_pct`** from the backend. The frontend mirrors the win% formula only for live engine lines, with tests pinned to the backend's values.
- **Promotion on the board is always to a queen.** Under-promotion would need a piece picker; v2 doesn't offer it (an explored variation, not the game itself).
- **PGN dates are shown as UTC dates.** A date-only header is stored as midnight UTC, which showed the day before in US timezones.
- **Upload flow:** upload → scan + verify → the game opens on the board, with this run's engine details under it and the synopsis starting by itself (as in v1). Games opened later load everything from the database; without a synopsis they show a "Write a synopsis" button.
- **The Moments tab** of the §5.1 layout arrives with M4.

**M3 (position-aware chat and Explain)**
- **Engine results by position:** `engine_results.position_key` is an indexed lookup column, not the unique key the plan said. A position recurs in a game with different move counters (repetitions) and v1's scan stores each occurrence, so uniqueness stays on the full FEN.
- **A position without verify/deep lines is analyzed in the browser first.** Chat and Explain send the result with the request; the backend checks it's for the replayed position and stores it without ever replacing the game's own analysis. If none is available it answers 409.
- **Explain runs on the chat's system prompt**, with its own instructions (`explain.md`) at the top of its user turn. A separate system prompt invalidated the whole cached prefix: measured on the owner's game, 0 cached tokens read and 10,963 written per Explain before, 12,435 read and 1,266 written after.
- **Caching:** three breakpoints (system prompt, game context, end of the conversation history).
- **The player in chat and Explain is the current profile** (Q5); the synopsis still uses the Elo stored with the game.
- **Null fields are left out of what the coach reads** (v1's `render`), so `branch_ply` only appears for variations.

**M4 (critical moments)**
- **What counts as giving the answer away:** the first move of every engine line for the moment's position that would grade "good" or better. The player's own tries are never counted, so the coach can discuss them.
- **Leak check by move number:** one of those moves written for the moment's own turn, or with no number, is a leak; the same SAN for another turn ("6. O-O" when the answer is "14...O-O") is not. Regenerate once with a note that names no move, then strip the move and log `moment_leak` (counted on the progress row).
- **Lines are cut, not dropped:** a line in the payload stops just before the first such move (it can come up later in the line as another move). The intro still shows what happens next. Found on the owner's games at the checkpoint, where whole lines were being removed.
- **Moment context:** game info, the annotated moves up to the moment, and the list of moments. No synopsis, chat history, key-moment lines or detector details. The system prompt stays shared, so it is cached across moments and games.
- **Game detail hides an unsolved moment's position:** its stored engine results and best move are left out until the moment is solved or revealed.
- **Progress keeps the exercise's messages** (`moment_progress.messages`), so a returning player sees where they were. A stored intro or wrap-up is shown again without a new call. The wrap-up is stored with the last moment.
- **Questions during a moment** get the same per-game allowance as chat questions (30).
- **The deep search of the moment's position** runs once per page visit and is sent with each attempt or "Show me". The backend checks it against the replayed position and keeps the first one.
- **`cli backfill`** rebuilds analyzed games' summaries from their stored engine results (no engine runs), so v1 games get their moments.
