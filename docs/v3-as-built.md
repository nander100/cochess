# CoChess v3: as built

What v3 became, measured against `SPEC_V3.md`. Every decision behind a difference is in the decision log of `docs/PLAN_V3.md`, with who made it. Branch `v3` (pushed 2026-11-06, not yet merged into `main` or deployed).

## What v3 added, by milestone

| Milestone | Built |
|---|---|
| M1 UI foundation | No color is ever pre-selected (upload and assessment); "Change color" and "Delete game"; design tokens with light/dark/system themes; shared UI components; settings (`user_settings`, `GET/PATCH /api/settings`); keyboard shortcuts with a `?` overlay. |
| M2 Variations, export | Variations played on the board are saved (`game_variations`, `GET/PUT /api/games/{id}/variations`); `GET /api/games/{id}/export.pgn` with variations, NAGs, `[%eval]` and moment notes; round-trip tests. |
| M3 Coach annotations | `<board arrows squares/>` tags checked against python-chess and the engine data (§6.2) before they're drawn; dropped ones go to `annotation_log`; leak check covers arrows. |
| M4 Walkthroughs | Forced `line_walkthrough` tool call; per-step facts (`analysis/move_facts.py`), each step searched at the **verify** tier (owner decision); cached per player and line (`walkthroughs`); stepper with W shortcut. |
| M5 Plain language, playback | One markup pass for every reply (`coach/markup.py`): move tags rendered as words, line links instead of written-out lines, bare-notation and moves-in-a-row checks with one regeneration; detail level Plain/Standard/Technical; line playback that stops at the backend's settle point (`analysis/settle.py`) with a caption. |
| M6 Dashboard | The Games page is the dashboard: focus areas with examples and Lichess puzzle-theme chips, games to continue, mistake-type and accuracy charts (Recharts, lazy-loaded), recent games, the assessment card; `GET /api/dashboard` with `game_stats` (200 games in under 300 ms). `{{puzzle:theme}}` tags in coach text. |
| Owner request | Chess.com and Lichess usernames on the profile; the backend detects the player's color from them in every PGN (upload, assessment, import). |
| M7 Game import | Chess.com and Lichess (`app/importers/`), `POST /api/import` review table, `games.external_source/external_id`, import panel on the Games page and in the assessment, daily cap respected. |
| M8 Harden and ship | Code splitting (main chunk 579 → 314 kB), a production Docker smoke test and the fixes it found, e2e flows for every v3 feature, README and `docs/DEPLOY.md` for v3. |

New routes: `GET/PATCH /api/settings`, `PATCH` and `DELETE /api/games/{id}`, `GET/PUT /api/games/{id}/variations`, `GET /api/games/{id}/export.pgn`, `POST /api/games/{id}/walkthrough` (SSE), `POST /api/lines/{id}/playback`, `GET /api/dashboard`, `POST /api/import`. New SSE events: `annotation`, `move`, `line_link`, `puzzle`, `walkthrough`.

Migrations 0009 to 0018: `user_settings`, `game_variations` and `games.variations_saved_at`, `annotation_log`, `walkthroughs`, coach detail level and playback speed, `line_links` and `baseline_reports.moves`, `game_stats`, a repair for `baseline_reports.moves` (0016), usernames, and `games.external_source/external_id`.

## Where v3 differs from SPEC_V3

- **Color (§4.6):** the player picks, or the backend detects it from the player's own Chess.com/Lichess username in the PGN's White/Black headers. A username match is not a default; no match means the player picks. (Owner, 2026-11-06.)
- **Dashboard (§8.1):** on the Games page rather than a separate home route; filters apply to game lists and accuracy, while focus areas and the mistake chart use all games.
- **Puzzles (§8.2):** `allowed_tactic` (not in the spec's table) maps to Defensive move and Fork.
- **Import (§10):** both platforms (owner reversed the M0 "Lichess only" decision); linked accounts are the profile usernames (no `linked_accounts` table or `/api/me/linked-accounts`); the review table fills in the detected color instead of only hinting; imported games count toward the daily cap; the platform rating isn't shown next to the Elo field.
- **Walkthroughs (§7.2):** steps are searched at the verify tier, not the scan tier.
- Smaller choices (annotation rules, line-link references per task, playback captions, export details) are in the decision log.

## Done-conditions (SPEC_V3 §12)

| Condition | Status | Evidence |
|---|---|---|
| No color pre-selected; no game submitted without one | Met | API tests (missing color is a 422, or `needs_color` in the assessment), Vitest form tests, e2e `color.spec.ts` (three flows, including username detection). |
| No raw notation outside move tags; no more than one move in a row | Met in tests and real replies | `coach/markup.py` checks with one regeneration then removal; plain-language tests; M5 checkpoint replies at three detail levels. |
| A newer player (under 1000) can follow a Plain-level synopsis | **Needs the owner** | Ask a trusted newer player to read one Plain synopsis of their own game. |
| Playback stops where the difference shows, on 5 owner lines, never mid-exchange | **Needs the owner** (3 shown at M5) | Settle-point tests (piece win, even exchange, mate, quiet line); M5 screenshots of 3 playbacks. Two more lines to review. |
| No arrow drawn that fails validation; green only on good moves | Met | Annotation tests for every arrow type and color (including a green arrow on a bad move rejected); `annotation_log` in the M3 demo shows 13 bad tags dropped (8 malformed, 5 not in the data) and none drawn. |
| The owner agrees with walkthroughs on 5 lines | **Needs the owner** (3 shown at M4) | M4 checkpoint walkthroughs; two more lines to review. |
| Dashboard focus areas match the owner's baseline report and recent games; loads within target | Load target met; match **needs the owner** | 200-game test under 300 ms; M6 screenshots of the owner's dashboard. |
| Zero `moment_leak` incidents, including annotations | Met so far | `moment_progress.leaks` sums to 0 in the owner's dev database (10 practiced moments) and in the M3/M5 demo databases; leak tests for text, move tags, line links and annotations. |
| Exported PGNs re-import cleanly | Met | Backend round-trip tests; e2e `variations.spec.ts` re-imports an export as another player and gets the same moves and final position. |
| All tests, lint, type checks and e2e pass | Met | See the final check run in the M8 report. |

Carried from v2 (PLAN_V3 adjustment 10): **the owner steps through critical moments on 5 games on the deployed app.** Still open; it needs the v3 deploy.

## Performance

- Dashboard: 200 games in under 300 ms (test).
- Frontend bundle: main chunk 314 kB (98 kB gzipped); the game page, assessment, profile and charts load on demand.
- Analysis in the browser (production build, multi-threaded Stockfish 19 lite, a laptop): about a minute per game for scan and verify; two imported games took 2 minutes 14 seconds including the import.
- Import: one request to Lichess; for Chess.com one request for the archive list plus one per month read (at most 12), one at a time.

## Known issues and gotchas

- **Console noise on game pages:** chessground sets `style="color-scheme:light only"` on its SVG layers, which the production CSP (`style-src 'self'`) blocks; the same rule comes from our stylesheet, so nothing looks different, but the console shows four CSP lines per game page. The `404` for `/api/onboarding/report` before a baseline report exists is expected.
- **Dev server and migrations:** `uvicorn --reload` applies a migration the moment its file is written, so a migration must be written once, complete (0016 repairs a dev database that ran an early 0014).
- **Chess.com contact:** set `IMPORTS__CONTACT` in production; without it the User-Agent is just `CoChess`.
- **Single process:** the import cooldown is kept in memory, per backend process; fine for one process (the deploy runs one).
- **Imported games not the player's:** a game in an import where neither username appears (renamed account) asks for a color and blocks the assessment's Add until chosen or removed from the paste box.
- `npm run e2e:real` overwrites `backend/tests/fixtures/engine/<game>.json`; restore it unless re-capturing.
- The owner's local Docker app (compose project `cochcess`, port 8080) still runs a pre-v2-M5 build with duplicate games; it was not touched.
