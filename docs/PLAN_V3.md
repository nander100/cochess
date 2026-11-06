# CoChess v3 — Implementation Plan (M0)

Status: **awaiting owner approval at the M0 checkpoint (2026-11-04).** Sources: `SPEC_V3.md`, `docs/v2-as-built.md`, `docs/v2-handoff.md`, the code at branch `v3`. Baseline checks at M0: backend 578 tests passing (98% coverage), ruff and mypy clean; frontend Vitest, oxlint and typecheck clean.

## Context

v2 is merged and tagged; branch `v3` is clean. SPEC_V3 §12 M0 asks for: `docs/v2-as-built.md`, an implementation plan for M1–M8, recommended spec changes, and the M7 decision. The v2 handoff adds starting conditions: the color pre-select bug (top fix), no way to fix a wrong-side game or delete one, onboarding game removal never built, owner's local Docker DB holds duplicates (don't touch), SPEC_V2 done-condition still open (owner stepping through 5 games' moments).

**Owner decisions already made (this session):**
- M7: **build Lichess import only; Chess.com on hold.**
- Wrong-side games: **add both "Change color" and "Delete game"** (in M1, right after the color fix).

## M0 deliverables

1. **`docs/v2-as-built.md`** — from the exploration already done: all 25 routes + SSE events (`status/text/done/error/engine_request/moment`), the 14 tables and migrations 0001–0008, payload shapes (`CoachPayload`, `PlayerPayload`, `MomentPayload`), withholding (`coach/moments.py::_call/_scrub/_scrub_player/_context`, banned = all `good_first_moves`), validation (`coach/validate.py` regex `_SAN`, `find_invalid`, `find_leaks` by move number), regenerate-once pattern in every coach path, tendency math (`analysis/tendencies.py`), grading (`analysis/moments.py::grade`), engine checks (`analysis/engine.py::check_batch/check_for_position/_check_line_is_legal`), and the handoff's deviations. Note discrepancies found: chat `engine_lines` untrimmed despite payload.py:176 comment; `ParsedRow.suggested_color` unused by the frontend; coach text is buffered (not streamed) end-to-end.
2. **`docs/PLAN_V3.md`** — the M1–M8 plan below, the adjustments list, and a decision log (as PLAN_V2 did).
3. **`CLAUDE.md`** — replace with `CLAUDE_3.md`, corrected to the real code, then delete `CLAUDE_3.md`. Corrections: dev server `uvicorn app.main:create_app --factory`; frontend lint is oxlint (`--deny-warnings`), add `npm run typecheck`/`build`/`e2e`; eval conversion lives once in frontend `engine/score.ts::toWhitePov` (not backend); package is `@lichess-org/chessground`; keep v2's Stockfish build note, CLI commands (`assign-games`, `backfill`), env `__` nesting note, ruff RUF003 and oxlint set-state notes; real frontend layout keeps `components/`, `analysis/`, `onboarding/`; importers = `lichess.py` only.
4. Commit docs (`docs: v2 as-built, v3 plan`), then **stop at the ✅ M0 checkpoint**.

## Adjustments to SPEC_V3 (recommended spec changes, for owner approval at M0)

1. **Rendering tokens inside markdown.** Coach text is rendered with react-markdown; splitting markdown at `char_offset` breaks formatting. Backend replaces each validated tag with a backend-generated placeholder link (e.g. `[knight takes on e5](cc:move/3)`), and the frontend maps `cc:` links to components via react-markdown's `components`. Events still carry `char_offset` per §11.1; the frontend never sees raw `{{...}}`/`<board>`. Invalid tags are removed before text is sent.
2. **Move tags may carry a move number**: `{{move:14...Qxd4}}` (optional). Keeps v2's by-move-number leak check precise; an unnumbered tag naming a banned SAN counts as a leak.
3. **Annotation leak set = v2's banned set** (every move grading good or better, not only the best), matching v2's stricter withholding. In practice no green arrows during an unrevealed moment.
4. **Moment messages live in `moment_progress.messages`**, not `chat_messages`; store tokens/annotations/line links there too (spec §11.2 only names chat_messages).
5. **`coach_detail_level` nullable = "auto from rating band"**, so changing Elo updates it until the user picks explicitly.
6. **Dashboard denormalization:** add accuracy, phase accuracy, and moments total/solved as columns (or a `game_stats` table) filled on analysis + backfill, instead of parsing `game_summaries` JSON for 200 games.
7. **Typing indicator** = existing "Coach is writing…" status (text is buffered by design for validation).
8. **Coach client tool support:** `tools` is hardcoded to `analyze_position` in `chat.py::_request` and in `tests/coach_fakes.py`; generalize both for the forced `line_walkthrough` tool.
9. **M7 scoped to Lichess**; Chess.com deferred (small `importers/base.py` interface so adding it later is cheap).
10. **Additions not in the spec:** Change color + Delete game (M1); carry the open SPEC_V2 done-condition (5 games' moments on the deployed app) into the M8 checklist.

## M1–M8 implementation plan

**M1 — Color fix, wrong-side recovery, UI foundation**
- Commit 1 (color fix, shippable alone): `GameInput.tsx:12` → `useState<Color | null>(null)`, color radios before the PGN box, PGN box + Analyze disabled with helper "Choose the color you played first."; `PasteGames.tsx:61` drop `?? 'white'`, submit disabled until every row has a color, highlight missing rows; backend `ParsedRow.user_color` stops falling back to the suggestion (`suggested_color` stays as a hint only); drop the `color="white"` parameter default in `tests/api/test_game_views.py:21`. Tests: API 422 on missing color (games + onboarding submit), Vitest form can't submit, Playwright neither radio checked on load.
- Commit 2: `PATCH /api/games/{id}` `{user_color}` → rebuild via a single-game variant of `db/games.py::rebuild_summaries` (no engine rerun), reset that game's `moment_progress`, refresh tendencies. `DELETE /api/games/{id}` cascades engine_results, summaries, chat, moments, theme facts, then refreshes tendencies; onboarding "remove game" uses it. 404 tests for other users. Confirm dialog in the UI.
- Then: tokens (`src/styles/tokens.css`, light/dark/system via `data-theme`, default dark, WCAG AA), migrate `styles.css` (11 raw hexes) to tokens; `src/ui/` shared components (Button, IconButton, Tabs, Card, Tooltip, Modal, Toast, Skeleton, EmptyState, ErrorState) replacing the `coach-writing`/`run-error` patterns; one chess-meaning color+glyph map; `user_settings` table + `GET/PATCH /api/settings` + Settings page; `src/shortcuts/` registry generalizing `board/useArrowKeys.ts` (keeps `isTyping`), `?` overlay; a11y basics. Board color schemes/piece set: check licenses first. Ask before adding any font dependency.
- ✅ color-fix tests + Playwright screenshots of every page, light/dark, 1280/1920.

**M2 — Saved variations and PGN export**
- `game_variations` table, `GET/PUT /api/games/{id}/variations` replaying via `analysis/paths.py::resolve_path`; frontend debounced save from `board/tree.ts` branches (moment candidates from `withMomentLines` included); delete/promote menu in `MoveList.tsx` (display order only).
- PGN export in `analysis/pgn.py`: python-chess `Game` from stored PGN + variations, NAGs on user moves from summary classifications, `[%eval]` from stored evals, moment comments, original headers; `GET /api/games/{id}/export.pgn`. Round-trip test (mainline via `parse_pgn`, variations via python-chess reparse).
- ✅ exported fixture PGN opened in a Lichess-style viewer.

**M3 — Coach annotations**
- `coach/annotations.py`: parse `<board .../>`, limits (4/4/3), validate per §6.2 with python-chess + the engine lines for the message's position (chat: `api/turns.py::prepare_turn`; moments: scrubbed data) and `analysis/moments.py::grade` for colors; threats via `board.attacks`. Leak drop + `annotation_log` + regenerate once (extend `_problems` in `coach/moments.py`). New `annotation` SSE event via `api/coach.py::text_events`; persisted with the message. "Annotations" section in `coach_system.md`.
- Frontend: `Board.tsx` gains an `autoShapes` prop (user drawings stay separate), board-icon token per tag, hover draws that tag, clear on position change, redraw on return.
- ✅ transcripts + screenshots + annotation_log from a test run.

**M4 — Line walkthroughs**
- `analysis/move_facts.py` (pure; reuse `material.py` and detector attack helpers); `coach/walkthrough.py` with forced `line_walkthrough` tool; validation of step count, moves in text, per-step annotations; `walkthroughs` cache table; `POST /api/games/{id}/walkthrough`; per-step scan via `engine/runner.ts::analyzeAll` with progress, checked with `check_for_position`; `llm_usage` task `walkthrough`.
- `src/walkthrough/` stepper (pattern from `MomentStepper.tsx`), all entry points + W, save as variation.
- ✅ walkthroughs of 3 lines from owner games.

**M5 — Plain language and line playback**
- Prompt rewrite across all task files (§9.2), detail level in `PlayerPayload`. `validate.py`: move-tag parsing, bare-notation check (existing `_SAN` on tag-stripped text) → regenerate once → convert valid SAN to tags; multi-move check. SAN→words generator. Line-link resolver from payload data (`engine1-4`, `refutation`, `candidate`, `best` gated, `variation`), `line_links` table, `move`/`line_link` events.
- Settle point (pure, config thresholds) + caption from move facts; `POST /api/lines/{id}/playback`; background scan of linked lines; playback mode, controls, speed setting, reduced motion.
- ✅ 3 replies × 3 detail levels before/after, 3 playback sequences.

**M6 — Dashboard and puzzle links**
- `analysis/dashboard.py` + `GET /api/dashboard` with filters, denormalized stats + indexes, perf test (200 games, < 300 ms); puzzle tag validation; theme mapping in `config.py` (Lichess slugs verified). Frontend: Recharts (approved stack) on a lazy-loaded route; Dashboard becomes the home page (replaces `/` → `/games`).
- ✅ owner's real dashboard.

**M7 — Lichess import**
- `linked_accounts` (Lichess), `external_source/external_id` on games (unique per user); `importers/lichess.py` (httpx, user games export, max 50, perf type/since filters), rate-limit + error handling; review table reuses `PasteGames` with unselected colors + "Detected" hint/"Use detected colors"; dedupe by external id and fingerprint. Faked API in tests.
- ✅ importing the owner's recent Lichess games (confirm their Lichess username at M7).

**M8 — Harden and ship**
- Playwright flows: color selection, change/delete game, annotations, walkthrough, playback, dashboard, export, Lichess import (faked); dashboard perf; Vite code splitting (fixes the chunk warning); README/DEPLOY; EC2 deploy update. Checklist = v3 done-conditions + the carried SPEC_V2 item.

## Critical files (reuse)
- Backend: `app/coach/{validate,moments,client,chat}.py`, `app/api/coach.py` (`stream_coach`, `text_events`), `app/api/sse.py`, `app/analysis/{paths,pgn,material,engine}.py`, `app/analysis/moments.py::grade/good_first_moves`, `app/db/games.py::rebuild_summaries`, `app/config.py`, `tests/coach_fakes.py`, `tests/e2e_app.py`.
- Frontend: `src/components/GameInput.tsx`, `src/onboarding/PasteGames.tsx`, `src/styles.css`, `src/board/{Board,MoveList,tree,rules,useArrowKeys}`, `src/engine/runner.ts`, `src/analysis/chat.ts`, `src/api/{sse,types}.ts`, `src/pages/GamePage.tsx`, `src/moments/MomentStepper.tsx`.

## Verification
- M0: spot-check docs against code (route table vs routers in `app/main.py`, migrations vs `alembic/versions`); confirm baseline is green before any code: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`; `npm test`, `npm run lint`, `npm run typecheck`, `npm run e2e`.
- Every later milestone: the full check set plus that milestone's checkpoint evidence; never mark done with failures.

## Decision log

| Date | Decision | By |
|---|---|---|
| 2026-11-04 | M7 is built for **Lichess only**; Chess.com is on hold. | owner |
| 2026-11-04 | Wrong-side games get **both** "Change color" (rebuild from stored engine results) and "Delete game" (also used to remove onboarding games), in M1 after the color fix. | owner |
| 2026-11-04 | Adjustments 1–10 above approved with M0. | owner |
| 2026-11-04 | M1 brief: design in `docs/design/` (tokens.md, screens.md, source/); light theme by default; Settings as a section on Profile; proposed chess-meaning colors used until the M1 checkpoint; moment page restyled to Moment.dc.html with 2 tries and a neutral title ("Find a better move"). | owner |
| 2026-11-04 | "Get a hint" is enabled only after the player has made an attempt; it serves the next allowed hint, never the move. | owner |
| 2026-11-04 | Change color / Delete game come right after the color-fix follow-up, before the UI foundation. | owner |
| 2026-11-04 | Change color reuses every stored engine result and verifies only the new side's missing positions (the game goes back to `scanned`; the browser tops up on next open), so moments stay as reliable as a fresh upload. | owner |
| 2026-11-04 | The Analysis move list stays collapsed by default, leaving room for the coach conversation. | owner |
| 2026-11-04 | Fonts self-hosted (OFL woff2 from fontsource builds, no npm dependency); pieces: cburnett default + California alternative, licenses checked before adding. | Claude (plan accepted) |
| 2026-11-05 | M1 accepted ("start m2"). Not yet confirmed explicitly: the chess-meaning colors, Merida as the second piece set, Log out in the header and blunder red for errors. | owner |
| 2026-11-05 | M2 accepted ("approve M2"): promote semantics, `games.variations_saved_at`, a missed forced mate as `?`, and keeping variations on a color change are confirmed. | owner |

Add decisions made while building below this line, as in PLAN_V2 §7.

| Date | Decision (while building) | By |
|---|---|---|
| 2026-11-04 | Deleting a game keeps its `llm_usage` rows (game_id set to NULL) so the daily token budget still counts them. A deleted single game no longer counts toward the daily upload cap; acceptable while the cap is a testing limit. | Claude |
| 2026-11-04 | Changing an onboarding game's color moves it to the matching slot; if that slot already has 3 games, the change is refused (409) and the player removes a game first. | Claude |
| 2026-11-05 | Alternative piece set is **Merida** (GPLv2+), not California: lila's COPYING.md lists California as CC BY-NC-SA 4.0 (non-commercial), which v4's paid plan rules out. | Claude (owner to confirm at M1) |
| 2026-11-05 | The Games page holds the upload form (Main.dc.html); `/new` redirects there. `GET /api/games` adds `time_control_category`, `moments_total`, `moments_done` for the page's filter and "Moments to practice". | Claude |
| 2026-11-05 | Moments: `max_attempts` comes with each moment (the "Tries left" dots). "Get a hint" sends a fixed request through the existing moment question route, so the payload's withholding still applies. | Claude |
| 2026-11-05 | "Log out" sits beside the player's name in the header (the design has no place for it). Errors use the blunder red as `--color-danger` (the design has no error color). | Claude (owner to confirm at M1) |
| 2026-11-05 | The invite page shows "Invite accepted" with next steps instead of going straight in (Redeem.dc.html); a used link opened while logged in still goes straight in. | Claude |
| 2026-11-05 | Backend errors from actions show as toasts; refusals about what the player typed (bad PGN, duplicate) stay inline next to the form. | Claude |
| 2026-11-05 | Saved variations are derived from the board's tree: every explored line that leaves its parent's line is one variation (start path + moves); the list order is the tree order, so display order survives a reload. The browser sends the whole list (debounced 1 s); the backend replays every line and replaces the stored list. | Claude |
| 2026-11-05 | "Promote to main line of my notes" moves a variation to the front of the lines at its branch point. The game's own move always stays first, so off the game it becomes the first alternative; inside a variation it becomes that line's continuation (as on Lichess). | Claude (owner confirmed at M2) |
| 2026-11-05 | `games.variations_saved_at` (nullable, migration 0010) marks the first save. Before it, the board seeds finished moments' tries and best move as variations (v2 behavior); after it, the saved list is the whole truth, so a deleted moment line stays deleted. A schema addition beyond SPEC_V3 §11.2. | Claude (owner confirmed at M2) |
| 2026-11-05 | PGN export: NAGs as `$6`/`$2`/`$4` (?!, ?, ??); a missed forced mate is `?`. Original clocks are kept; `[%eval]` follows each mainline move; an `Annotator "CoChess"` header is added if missing. "Export PGN" sits with the game options and saves any waiting variations first. Changing color keeps variations; deleting the game deletes them. | Claude |
| 2026-11-05 | Annotation rules where §6.2 leaves room: a **threat** arrow must hit an enemy piece (controlling an empty square isn't a threat), and a move from the data is judged by its grade alone, so a red or green arrow on it can never pass as a "threat". Moves "in the data" are the game's move from P, the first move of each engine line, moves the coach analyzed from P with `analyze_position`, and a moment's tries. The chat payload has no saved variations, so "the next move of the user's variation" isn't available yet. | Claude (owner to confirm at M3) |
| 2026-11-05 | Annotation leak check: while a moment is unsolved, an arrow or highlight touching the from- or to-square of any move the player must find (adjustment 3) is a `moment_leak`; the one exception is an arrow that is exactly a move the player already knows (the game's move or one of their tries). The first leaky reply is logged, then regenerated once; a leak that survives is dropped and counted in `moment_progress.leaks`. | Claude (owner to confirm at M3) |
| 2026-11-05 | The synopsis and the baseline report have no board position: their board tags are removed and logged as `no_position` (the prompt tells the coach not to use them there). | Claude (owner to confirm at M3) |
| 2026-11-05 | The coach's history keeps its valid tags as rewritten markup (so it sees what it drew); the player gets `cc:board/N` placeholders; `annotation` events come after the text, before `done`. Chat entries now carry `path_uci` (a coach answer has its question's) so drawings come back after a reload. `annotation_log` rows survive a deleted game with `game_id` cleared, like token usage. | Claude |
| 2026-11-05 | Drawing: coach shapes use their own chessground brushes in the chess-meaning tokens (red = the blunder color), separate from the player's right-click brushes; a highlighted square is a circle, as on Lichess. A message's shapes are drawn on its position only; hovering a tag shows just that tag; clicking a tag while the board is elsewhere goes to the message's position. | Claude |
