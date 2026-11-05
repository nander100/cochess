# CoChess v2 — as built

Written at v3 M0 (2026-11-04) from the code at branch `v3` (= tag `v2` + docs). Records what v2 actually is, so v3 builds on facts rather than on `SPEC_V2.md`. Where this file and SPEC_V2 disagree, this file describes the code. The reasons behind the deviations are in `docs/PLAN_V2.md` §6–§7 and `docs/v2-handoff.md`.

Paths are relative to `backend/` or `frontend/`.

---

## 1. Endpoints

All routers are registered in `app/main.py`. Every user-data route depends on `get_current_user` and scopes by `user_id`; another player's game is a 404.

| Method | Path | Request → Response | Where |
|---|---|---|---|
| GET | /api/health | → ok | main.py |
| POST | /api/auth/redeem | `RedeemRequest` → 204 + session cookie | auth/routes.py |
| POST | /api/auth/logout | → 204 | auth/routes.py |
| GET / PATCH | /api/me | → / `ProfileUpdate` → `Profile` | api/profile.py |
| POST | /api/games | `CreateGameRequest{pgn, user_color}` → 201 `CreateGameResponse`; 422 `PgnErrorResponse`; 409 incomplete profile or duplicate | api/games.py |
| GET | /api/games | → `list[GameListItem]` | api/games.py |
| GET | /api/games/{id} | → `GameDetail` (moves, win% curve, accuracy, counts, stored engine results, verify FENs to resume, synopsis, chat history, moments + progress) | api/games.py |
| GET | /api/engine-config | → `EngineSettings` (tiers reach the browser from here) | api/engine.py |
| POST | /api/games/{id}/engine/scan | `EngineResultsRequest` → `ScanResponse` (verify FENs) | api/engine.py |
| POST | /api/games/{id}/engine/verify | `EngineResultsRequest` → `VerifyResponse`; builds the summary, theme facts, tendency snapshot | api/engine.py |
| POST | /api/games/{id}/synopsis | SSE | api/coach.py |
| POST | /api/games/{id}/chat | `ChatRequest{text, path_uci, engine_result?}` → SSE | api/coach.py |
| POST | /api/games/{id}/explain | `ExplainRequest{path_uci, engine_result?}` → SSE | api/coach.py |
| POST | /api/games/{id}/chat/engine_result | `EngineResultSubmission` → SSE (resumes the tool loop) | api/coach.py |
| POST | /api/games/{id}/moments/{index}/start · attempt · reveal · ask | SSE | api/moments.py |
| POST | /api/games/{id}/moments/wrap_up | SSE | api/moments.py |
| GET | /api/tendencies | → `TendencyReport` | api/tendencies.py |
| POST | /api/onboarding/parse | `ParseRequest` (+ per-game choices) → `ParseResponse` (rows, slot preview) | api/onboarding.py |
| POST | /api/onboarding/submit | `SubmitRequest` → `SubmitResponse` | api/onboarding.py |
| GET | /api/onboarding/status | → `OnboardingStatus` | api/onboarding.py |
| GET / POST | /api/onboarding/report | → `BaselineReport` / SSE (generate) | api/onboarding.py |

Not present: PGN export, game delete, change color, settings, variations. `GameDetail` does not return the PGN text.

The coach and moment routers apply `check_token_budget` (optional `USER_DAILY_TOKEN_LIMIT`). Single-game uploads are capped per player per rolling 24 h (`limits.max_games_per_day`); onboarding games don't count.

### 1.1 SSE

`app/api/sse.py` (`event`, `KEEPALIVE`, `chunks`) and `app/api/coach.py::stream_coach/_events/text_events`.

| Event | Data | Notes |
|---|---|---|
| `status` | `{message: "Coach is writing…"}` | first |
| (comment) | `: keepalive` | every `coach.keepalive_s` while the call runs |
| `engine_request` | `{request_id, tier: "deep", positions}` | chat only: the coach's `analyze_position` tool needs browser analysis |
| `moment` | `{grade, state}` or `{state: "revealed"}` | moment routes, before the text |
| `text` | `{text}` | ~200-char chunks of the **complete, validated** reply |
| `done` | `{invalid_moves_removed}` | |
| `error` | `{message}` | plain-language |

The reply is fully generated and validated before any `text` is sent; the frontend (`analysis/chat.ts::collect`) also gathers all chunks before rendering. Stored moment answers and the baseline report are re-sent without a new coach call.

## 2. Data model

Migrations `0001_v1_baseline` … `0008_baseline_reports` (Alembic, batch mode, naming convention on `Base.metadata`). The app runs `alembic upgrade` at startup; tests build the schema from migrations and assert it equals `Base.metadata`.

| Table | Key columns | Indexes / constraints |
|---|---|---|
| users | name, name_key, elo, time_control, playstyle | name_key unique |
| invites / sessions | user_id, token_hash, expires_at (+ used_at) | token_hash unique |
| games | user_id (**nullable**), pgn, user_color (`String(5)`, no default), elo (Elo at analysis), playstyle, headers JSON, time_control_category, user_result, played_at, status `uploaded→scanned→analyzed`, source `single`/`onboarding`, fingerprint | (user_id, played_at), (user_id, fingerprint) — not unique |
| engine_results | game_id, user_id, ply, fen, position_key, tier, depth, time_ms, lines JSON | unique (game_id, fen, tier); (game_id, position_key) |
| game_summaries | game_id PK, summary JSON (`GameSummary`) | |
| chat_messages | game_id, role, content JSON, path_uci JSON | game_id |
| llm_usage | game_id?, user_id, endpoint, task, model, token counts incl. cache read/write | |
| pending_tool_calls | request_id PK, game_id, tool_use, path_uci, positions, extra_results, tool_calls_used | |
| moment_progress | user_id, game_id, moment_index (1-based), state `intro/attempt/solved/revealed`, attempts JSON, revealed, **messages JSON**, leaks | unique (game_id, moment_index) |
| game_theme_facts | user_id, game_id, theme, subtype, ply, move_number, move_san, severity, phase, user_color, details | (user_id, theme) |
| tendency_snapshots | user_id, games_analyzed, report JSON | (user_id, created_at) |
| baseline_reports | user_id, text, invalid_moves_removed, game_ids | |

- `chat_messages.content` is `{"type": "chat", "blocks": [...], "display"?, "where"?}` (`db/chat.py::save_turn`); synopsis rows use `{"type": "synopsis"}`. Moment conversations are **not** in `chat_messages`; they live in `moment_progress.messages`.
- Accuracy, phase stats and moments live only inside `game_summaries.summary` JSON (`analysis/summary_models.py::GameSummary`: `accuracy`, `counts`, phase stats, `key_moments`, `moments`). There are no per-game stat columns.

## 3. Analysis pipeline

1. **Upload:** `analysis/pgn.py::parse_pgn` rejects non-standard starts, extra games, illegal moves; strips variations/comments; keeps `%clk`; re-exports a clean mainline (`_export_mainline`, internal only). Fingerprint (`analysis/game_info.py`) = players, result, UCI moves — no dates, no color. A duplicate is 409.
2. **Scan → verify (browser):** the frontend runs the tiers (`engine/runner.ts::analyzeAll`, `StockfishEngine.analyze`) and posts results. The backend checks them with `analysis/engine.py::check_batch` (exact expected FEN set) and `_check_line_is_legal` (every PV move legal), truncating to `max_line_plies`. Single-position results (chat/explain/moments) use `check_for_position` (position_key match, tier allowed). Evals are White-POV; the one conversion is frontend `engine/score.ts::toWhitePov`.
3. **Summary:** classification (`classify.py`), accuracy (Lichess formula), nine detectors (`detectors/__init__.py::run_detectors`: per-move hung_piece, allowed_tactic, missed_capture_or_check, missed_tactic, king_safety, pawn_structure, endgame_technique — only on inaccuracy-or-worse moves; game-level slow_development, pawn_structure, time_trouble), key moments, critical moments (`analysis/moments.py::select_moments`, 3–6).
4. **Persist:** `db/games.py::record_analysis` saves summary, theme facts, and refreshes the tendency snapshot. `db/games.py::rebuild_summaries` does the same from stored engine results without the engine (used by `cli backfill`; reads `game.user_color`, so it can serve a color change).

Path replay: `analysis/paths.py::resolve_path(game, path_uci, max_plies)` → `ResolvedPath` (FEN, SAN path, `pgn_to_move`, mainline/branch info).

## 4. Grading and moments

- `analysis/moments.py::grade`: **best** if the engine's top move or within `moments.best_margin` (0.02 win-chance drop); **good** if the drop is under `thresholds.inaccuracy` (0.10); otherwise `classify(drop)` → inaccuracy (0.10) / mistake (0.20) / blunder (0.30).
- `good_first_moves` = every move that grades good or better; this is the **banned set** while a moment is unsolved.
- Flow: intro → attempt (up to `max_attempts` = 2) → solved / revealed → wrap-up. During an active moment, free chat, Explain and the engine panel are disabled; leaving the Moments tab pauses it.
- Hints: `build_hints` from candidate facts; a hint naming a banned move is dropped.

## 5. Coach

- **Payload** (`coach/payload.py::CoachPayload`): `task`, `user_prompt`, `player` (`PlayerPayload`: elo, color, rating_band from `rating_band(elo)` <1000 beginner / ≤1800 intermediate / else advanced, playstyle, top tendencies, accuracy by phase/color), `pgn_to_move`, `position` (`PositionPayload`), `engine_lines: list[LineSummary{rank, eval, moves_san}]`, `game_summary`, `moment`, `baseline`. `render()` = instruction line + compact JSON.
  - Chat engine lines come from `api/turns.py::prepare_turn` and are **not trimmed** (the payload.py comment says "top 4 lines, 10 plies"; the code passes whatever was stored). Key-moment lines in the coach view are trimmed to `coach_engine_lines=2` × `coach_line_plies=6`.
- **Withholding (moments, `coach/moments.py`):** `_call` builds the banned set (good-or-better first moves minus the player's own tries) and, before reveal, sends no best move and no engine lines; `_scrub` cuts each refutation line just before a banned move and drops hints naming one; `_scrub_player` blanks tendency examples that match; `_context` sends only the game up to the moment, no synopsis, no chat history. Moment calls are single-turn and declare no tools.
- **Validation** (`coach/validate.py`): regex `_SAN` finds moves in prose (bare pawn moves only after a move number); `allowed_moves(payload)` collects every SAN in the data; `find_invalid` → `strip_moves` (`[move removed]`). `find_leaks(text, banned, move_number, white_to_move)` matches a banned SAN with no number or with the moment's own number and side.
- **Regenerate once** everywhere: synopsis (`coach/service.py`), baseline (`coach/baseline.py`), chat (`coach/chat.py::_finish`, tools off on retry), moments (`_problems` = leaks + invalid moves; `LEAK_NOTE`/`INVALID_NOTE`). A surviving leak is stripped, logged as `moment_leak`, counted in `moment_progress.leaks`.
- **Client** (`coach/client.py`): `CoachClient.complete(CoachRequest) -> CoachReply`; `AnthropicCoachClient` streams only to avoid HTTP timeouts and returns the final message; `output_config.effort`; API errors → `CoachUnavailableError`. Prompt caching: system prompt + game-context block (`system_blocks`), plus a history breakpoint. Tools: `analyze_position` (`coach/tools.py`), hard-coded in `chat.py::_request` (`tool_choice none` for Explain or when the 2-call limit is used).
- **Prompts** (`coach/prompts/`): `coach_system.md` (shared) + `synopsis.md`, `chat.md`, `explain.md` (instructions go in the user turn; runs on the chat system prompt to share the cache), `moment.md` (both moment tasks), `baseline_report.md`.
- **Models:** `COACH_MODEL_SYNOPSIS` (synopsis, baseline), `COACH_MODEL_CHAT` (chat, explain, moments).

## 6. Tendencies

`analysis/tendencies.py`: games most recent first, weight `0.5 ** (age / half_life_games)` (10). Facts count with severity weights (blunder 3, mistake 2, inaccuracy 1, concern 2, note 0). Per theme: per-move themes count each occurrence, game-level themes count once. `rate_per_game = Σ w·count / Σ w`, `score = Σ w·severity / Σ w`, sorted by score. Trend compares the weighted rate of the last 5 games with the 5 before (margin 0.25 per game; `None` under 10 games). Provisional under 5 games. Accuracy report = weighted mean overall, by color, by phase. Snapshots are stored per analysis in `tendency_snapshots`.

## 7. Onboarding

12 slots: White/Black × win/loss × 3 games (`games_per_slot`). `POST /parse` splits a paste (≤40 games, ≤600k chars), categorizes the time control with Lichess's formula (correspondence = wrong time control), and returns the slot preview from the server. `suggest_colors` proposes a color from the most frequent player name (None if ambiguous); `ParsedRow.user_color` currently **falls back to that suggestion**. Submit requires a color per game. Baseline report: backend counts openings (`opening_groups`), the coach writes 400–600 words. Removing a game from onboarding was never built.

## 8. Frontend

- Routes (`App.tsx`): `/redeem`, `/profile` always; once the profile is complete `/` (→ `/games`), `/games`, `/games/:gameId`, `/new`, `/onboarding`.
- Styling: one global `src/styles.css` (~970 lines) with a few `:root` variables and 11 raw hex colors; no themes, no dark mode.
- Board: `board/Board.tsx` wraps `@lichess-org/chessground` (brown board, cburnett pieces); **no drawable/auto-shapes** yet. Game tree `board/tree.ts` (immutable, node id = UCI path; `children[0]` continues the line) lives in React state and is **not persisted**; only moment attempts/best lines are rebuilt from the server (`GamePage.tsx::withMomentLines`). Promotion is always to a queen.
- Keyboard: only ←/→ (`board/useArrowKeys.ts`, ignores typing) and Enter in chat.
- Coach text: `react-markdown` (no raw HTML) in ChatPanel, MomentStepper, Synopsis, onboarding report.
- States: plain `<p className="coach-writing">` / `<p className="run-error" role="alert">`, a native `<progress>` wrapper; discriminated-union load states.
- Color bug: `components/GameInput.tsx:12` starts at `'white'`; `onboarding/PasteGames.tsx:61` falls back to `'white'` on submit; `ParsedRow.suggested_color` is never read.
- Dependencies: react 19, react-router 7, chessground 10.5, chess.js 1.4, react-markdown 10, stockfish 19 (lite builds). No Recharts.

## 9. Tests at v2 (re-run at v3 M0, all green)

Backend 578 pytest (98% coverage), ruff + mypy strict clean. Frontend Vitest, oxlint (`--deny-warnings`), typecheck clean. Playwright: 3 flow specs (onboarding, coaching, errors) against a scripted engine (`src/test/scriptedEngine.ts`) and scripted coach (`backend/tests/e2e_app.py`), plus the real-engine `e2e/analysis.spec.ts`. Coach tests use `tests/coach_fakes.py::FakeCoachClient` (text, `ToolCall` for `analyze_position`, or exception).

## 10. Differences from SPEC_V2 that matter for v3

- Withholding is stricter than the spec (whole good-or-better set; lines cut, not dropped). v3's annotation and line-link leak checks should use the same banned set.
- Moment messages are stored in `moment_progress`, not `chat_messages`.
- Coach replies are buffered, not streamed; offsets in v3's new SSE events can refer to the final text.
- `analyze_position` is the only tool and is hard-coded in the chat loop and the fake client.
- Statuses: `uploaded → scanned → analyzed` (no separate verified/summarized).
- `games.user_id` nullable; `cli assign-games` fills it.
- No game delete, no change color, no onboarding removal (v2-handoff known gaps).
