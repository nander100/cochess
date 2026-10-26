# CoChess v1 — as built

Written at v2 M0 (2026-10-26) from the code at tag `v1` (`15a55a9`). It records what v1 actually does, so v2 plans against the real code. Where this file and `SPEC.md` disagree, this file describes reality. Approved v1 decisions are numbered Q1–Q29 in `docs/PLAN.md`; references like "Q22" point there.

Health at `v1`: 304 backend tests (98% line coverage), 94 frontend tests; ruff, mypy (strict), oxlint and `tsc -b` clean.

---

## 1. Architecture

As in SPEC §4: the backend (FastAPI + python-chess) owns parsing, SAN, legality, classification, detectors, the summary, and every Claude call. The browser runs Stockfish only on FENs the backend hands it, and posts results back. Single page, no router, no accounts.

- App factory: `app.main:create_app(settings?, coach_client?)`. Importing `app.main` has no side effects. Tests inject settings (in-memory SQLite) and a fake `CoachClient`.
- Schema is created with `Base.metadata.create_all` at startup. There is no Alembic (Q12).
- Middleware: an access gate and COOP/COEP headers on every response.
- Docker: backend (uvicorn) plus frontend (nginx serving the Vite build). nginx sends COOP/COEP and a wasm MIME type, proxies `/api` with buffering off for SSE, and has a 180 s read timeout. SQLite lives on the `cochess-data` volume.

## 2. HTTP API (actual)

Every `/api/*` path except `/api/health` requires the `X-Access-Code` header (compared with `hmac.compare_digest`). An empty `ACCESS_CODE` turns the gate off and logs a warning.

| Method & path | Body | Returns | Differs from SPEC §9 |
|---|---|---|---|
| `GET /api/health` | — | `{ok: true}` | — |
| `GET /api/engine-config` | — | `EngineSettings` (threads, hash, the 3 tiers) | **New** (Q5): the browser reads tiers from backend config |
| `POST /api/games` | `{pgn, user_color, elo (100–3000), playstyle? (≤500)}` | 201 `{game_id, positions[{ply, fen_before, san, uci, clock_s}], final_fen, final_is_terminal}`; 422 `{detail: {code, message, move_number}}`; 429 at the daily cap | Adds `final_is_terminal`, 429 |
| `POST /api/games/{id}/engine/scan` | `{results: EngineResult[]}` | `{verify_fens: [...]}` | Batch must be exactly the expected FENs |
| `POST /api/games/{id}/engine/verify` | `{results: EngineResult[]}` | `{summary_ready, counts, accuracy}`; 409 if scan is missing | Builds and stores the summary |
| `POST /api/games/{id}/synopsis` | — | SSE | Returns the stored synopsis if one exists (generated once per game) |
| `POST /api/games/{id}/chat` | `{message}` (1–2000 chars) | SSE; 429 after 30 questions per game | **Always SSE** (Q26); `engine_request` is an SSE event, not JSON |
| `POST /api/games/{id}/chat/engine_result` | `{request_id, results}` | SSE; 404 if not pending; 422 bad results | — |

There is no `GET` for a game: nothing can be reopened after the page closes.

**SSE contract** (`app/api/coach.py`): first `event: status {"message": "Coach is writing…"}`, then `: keepalive` comments every 10 s while Claude works, then either `text` chunks (~200 chars) followed by `done {invalid_moves_removed: [...]}`, or `engine_request {request_id, tier: "deep", positions: [{fen, label: "position"|"after_candidate"}]}`, or `error {message}`. **Text is only sent after move validation** (Q22: buffer, validate, then stream).

**Limits** (config): `max_pgn_chars` 100,000, `max_plies` 600, `max_games_per_day` 10 **for the whole server** (testers share one code), `chat_max_messages` 30 per game, `chat_max_message_chars` 2000, `chat_max_tool_calls` 2 per message.

## 3. Database (SQLite, `create_all`)

| Table | Columns | Notes |
|---|---|---|
| `games` | `id` (UUID string PK), `pgn` (main line only, `%clk` kept), `user_color`, `elo`, `playstyle`, `headers` JSON, `created_at` | The profile is stored per game. No user or status columns |
| `engine_results` | `id`, `game_id` FK, `ply` (nullable, informational), `fen` (full FEN), `tier`, `depth`, `time_ms`, `lines` JSON, `created_at` | Unique (`game_id`, `fen`, `tier`). Re-submitting replaces the row. Deep-dive results from chat are stored here too |
| `game_summaries` | `game_id` PK/FK, `summary` JSON, `created_at` | Rebuilt on every verify |
| `chat_messages` | `id`, `game_id`, `role`, `content` JSON, `created_at` | `content.type` is `"synopsis"` (`{text, invalid_moves_removed}`) or `"chat"` (`{blocks: [...]}`, raw Anthropic content blocks including thinking signatures and tool_use/tool_result, replayed verbatim). The player's message is stored as the rendered payload text (instruction line + JSON), **not** as plain text |
| `pending_tool_calls` | `request_id` PK, `game_id`, `tool_use` JSON, `positions` JSON, `extra_results` JSON, `tool_calls_used`, `created_at` | At most one per game; a new chat message cancels it with an error tool_result |
| `llm_usage` | `id`, `game_id`, `endpoint` (`synopsis`/`chat`), `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `created_at` | — |

## 4. Engine (browser)

- `stockfish@19.0.1`, the **lite** builds (1.7 MB wasm): `stockfish-19-lite` (multi-threaded) if `crossOriginIsolated`, else `stockfish-19-lite-single` (Q6). Copied to `public/engine/` by `postinstall`. Threads = `min(hardwareConcurrency − 1, 4)`, Hash 64 MB.
- `src/engine/search.ts::search(transport, fen, tier)`: `setoption MultiPV`, `position fen`, `go infinite`, then `stop` once **both** min time and min depth are reached, or at the hard cap. It waits 3 s for `bestmove` after `stop`. Lowerbound/upperbound and `info string` lines are ignored. Depth counts once multipv 1 reports it. It returns depth, time and the lines by multipv. There is **no cancellation and no streaming callback**.
- `StockfishEngine` runs searches strictly one at a time through a promise queue. `EngineTransport {send, onLine}` is the seam; `src/test/fakeTransport.ts` scripts it in tests.
- `score.ts::toWhitePov` is the only side-to-move → White conversion (Q4). It throws on `mate 0`.
- Tiers (`app/config.py::EngineSettings`, matching SPEC §5.3 values):

| Tier | MultiPV | Min time | Min depth | Hard cap | Plies kept |
|---|---|---|---|---|---|
| scan | 1 | 250 ms | 12 | 1000 ms | **1** (only the best move is kept) |
| verify | 4 | 1500 ms | 18 | 3000 ms | 10 |
| deep | 4 | 3000 ms | 22 | 8000 ms | 10 |

- Scan covers every distinct `fen_before` plus the final position, unless it's checkmate/stalemate (Q8: scored from the board, `Evaluation.checkmated`).
- **Verify selection** (`analysis/selection.py`): every user ply with drop ≥ inaccuracy (0.10 wc), plus the 3 largest swings by either side, capped at 15 plies (largest kept). Before and after FENs are deduped. This means all of the user's errors are verified unless more than 15 qualify.
- **Backend checks** (`analysis/engine.py::check_batch`): the batch must be exactly the expected FEN set (no extra, none missing, no duplicates), the tier must match, `len(lines) ≤ multipv`, each line is truncated to `max_line_plies`, every PV move must be legal (python-chess), ranks must be 1..n, and exactly one of `eval_cp`/`mate` must be set per line, never `mate 0`. FENs are compared as **exact full-FEN strings**.
- Classification uses the highest tier per FEN (`best_by_fen`: deep > verify > scan).

## 5. Classification, accuracy, phase

- `wc = 2/(1+exp(-0.00368208·cp)) − 1` with **cp clamped to ±1000** first (Q9). Mate and delivered checkmate → ±1 (Q10). Win% = 50 + 50·wc.
- Thresholds on the mover's wc drop: inaccuracy ≥ 0.10, mistake ≥ 0.20, blunder ≥ 0.30. **Both sides** are classified (Q20); detectors run only on the user's moves.
- **Missed mate** (Q21 plus the M3 review): the mover had a forced mate before, has none after, **and** the mover's win% after is below 90. Label `missed_mate` unless the move is also a blunder (a blunder keeps the blunder label; counts include it under both).
- **Accuracy is Lichess's real formula** (Q11), not the spec's simple mean: per move `103.1668·exp(−0.04354·Δwin%) − 3.1669 + 1`, clamped 0–100, and 100 if win% didn't drop. A side's accuracy = (volatility-weighted mean + harmonic mean) / 2, with window `clamp(moves//10, 2, 8)` and weights = window stdev clamped to 0.5–12. Phase accuracy uses the same aggregate over that phase's moves.
- Phase: SPEC §6.2 exactly, evaluated on the position **before** the move.

## 6. Detectors (nine, not eight)

Pure functions in `app/analysis/detectors/`. Per-move detectors run only on user moves that are inaccuracies or worse, or missed mates (`MoveContext.flagged`). A missed mate counts as "at least a mistake". Material is N=B=3, R=5, Q=9, and "within N plies" extends one ply when the Nth ply is a capture (Q14).

| Detector | Fires on | As built |
|---|---|---|
| `hung_piece` | flagged | A user piece (not the king) is attacked and undefended, or attacked by a cheaper piece, and material lost **measured from before the user's move** over 1+3 plies is ≥ 2, so an even trade isn't flagged. Details: `piece`, `square`, `lost_to` (the capture in the reply line), `material_lost` |
| `allowed_tactic` | **new** (M3 review), mistake+ | The opponent's best reply wins ≥ 2 or mates within 5 plies. Skipped when `hung_piece` already fired. Details: `subtype`, `reply_move`, `line`, `material_lost`, `allows_mate` |
| `missed_capture_or_check` | mistake+ | The best move was a capture/check and the played move was neither. Details: `best_move`, `kind`, `material_won` (5-ply window) |
| `missed_tactic` | flagged | The best line wins ≥ 2 or mates within 5 plies, and the played move ≠ best (Q13). Subtype priority: back_rank (mate on the back rank, or a first-move heavy-piece check on it) → fork → pin/skewer → discovered_attack → combination. Details: `subtype`, `best_move`, `line`, `material_won`, `forces_mate` |
| `king_safety` | mistake+ | A pawn move inside the king's shield, or a file next to the king opened, or a reply-line check within 3 plies where the drop isn't a material grab (Q15). Details: `pawn_moved`, `opened_files`, `check_sequence` |
| `pawn_structure` | flagged | Created a doubled, isolated, or backward pawn. **Game-level fact always emitted**: structure at the end of the opening (Q17), severity `note` |
| `endgame_technique` | mistake+ in the endgame | `threw_win` (≥ 70 → ≤ 55 win%), `passive_king` (Chebyshev distance ≥ 3 from the center while the best move was a king move; details include `best_move`), `allowed_passer` |
| `slow_development` | game-level | Spec rule. Severity `note`, or `concern` if the opening cost ≥ 0.15 wc (Q18) |
| `time_trouble` | game-level | Emitted **whenever `%clk` is present**: `concern` if any mistake/blunder came on a low clock, else `note` |

`ThemeFact` = `{theme, ply?, move_number?, move_san?, severity (inaccuracy|mistake|blunder|note|concern), eval_before?, eval_after?, details}`. **It has no `phase`, `subtype` column, or user color field.** Subtype lives in `details` for some themes only.

**Details that name the engine's best move** (relevant to v2 withholding): `missed_tactic.best_move`/`line`, `missed_capture_or_check.best_move`, `endgame_technique(passive_king).best_move`.

## 7. Game summary (stored JSON)

SPEC §6.5, with these differences:
- `user` is `{color, elo, playstyle}`, taken from the game row.
- `phase_breakdown[phase]` = `{moves, accuracy, inaccuracies, mistakes, blunders}`.
- `key_moments` (≤ 8): the user's missed mates, then blunders, then mistakes (by drop), then the 3 biggest swings by either side not already in. They are sorted chronologically. Each has `best_move_san`, `engine_lines` (all verify lines from the position before, full 10 plies, SAN) and **`line_after_san`** (new: the engine's best line after the move actually played, i.e. the refutation).
- Inaccuracies are **not** key moments unless they are one of the top swings.
- `move_list` and `eval_curve` are stored (eval strings only, no win%).

## 8. Coach

**Models and settings** (owner's cost review, "option B"): `COACH_MODEL_SYNOPSIS=claude-sonnet-5-5` at effort `low`, `COACH_MODEL_CHAT=claude-haiku-5-5` at effort `medium`. Effort is sent as `output_config={"effort": ...}`. Thinking is on, and `max_tokens` is 8000 for the synopsis and 6000 for chat. About $0.02 per game.

**Prompts** (`app/coach/prompts/`): `coach_system.md` holds the shared rules, plus `synopsis.md` or `chat.md`. Each call sends only its own task file. The shared prompt has a **"Reasoning about the position"** section (commit `1e85820`): the coach may reason about plans, activity, weaknesses and why moves work, but moves and evals stay the engine's and it must not contradict them. This is a deliberate loosening of SPEC §7.3's "never calculate". The synopsis has a ≤ 300-word target and logs a warning above 350.

**Payload** (`app/coach/payload.py`, cost-reduced in `1b6d56b`):
- `CoachPayload {task: "synopsis"|"chat", user_prompt?, player {elo, color, rating_band, playstyle, tendencies: []}, pgn_to_move?, fen?, engine_lines?, game_summary?}`. `fen` and `engine_lines` exist in the model but are **never filled** in v1.
- `pgn_to_move` is an **annotated movetext** (`10. d4?? Bb4 11. a3 O-O?`) that replaces `move_list` and `eval_curve`, which are excluded from what the coach sees.
- Key-moment lines are trimmed for the coach to **2 lines × 6 plies** (`coach_engine_lines`, `coach_line_plies`). The stored summary keeps everything.
- Rendered as one instruction line plus compact JSON.

**Synopsis**: a single call with system = `[system prompt (cache_control)]` and user = the payload. Validation, then regenerate once with a note, then strip invalid moves to `[move removed]`. Stored once in `chat_messages` as type `synopsis`.

**Chat** (`app/coach/chat.py`):
- System = `[system prompt, game context]`, with **one cache breakpoint on the last block**, so both are cached together. The game context = the annotated movetext, the trimmed summary, **and the stored synopsis text** (Q25).
- Each user turn carries only `{task, user_prompt, player}`. The full history is replayed from `chat_messages`.
- Tool `analyze_position {ply (required), candidate_move_san?}`. The backend checks the ply is in 1..N+1 and not terminal, and that the candidate is legal (python-chess). Bad input → an `is_error` tool_result, and the loop continues.
- A valid call saves `pending_tool_calls` and emits `engine_request` with positions `[position, after_candidate?]`. A candidate that mates or stalemates is scored from the board, not searched.
- The browser runs the deep tier and posts `/chat/engine_result`. The results are checked against the pending FENs, stored, and turned into `AnalysisToolResult {ply, move_number, side_to_move, moves_before, played_in_game, eval, best_lines[], candidate {move_san, eval_after, classification_if_played, is_best_move, best_replies[]}, depth}`.
- At most 2 tool calls per message; after that `tool_choice: none`. Only one tool call is served per turn; extras get an error.

**Validation** (`app/coach/validate.py`):
- Regex tokens: piece moves, pawn captures, promotions, castling, anything with `+`/`#`, and bare pawn moves **only after a move number** (`14. d4`). Bare squares in prose are not moves (Q23).
- Normalization strips `+`/`#` and maps `0-0` to `O-O`. Validation is **set membership over all SAN found anywhere in the payload** (and in tool results), not per position.
- `user_prompt` is excluded from the allowed set.

**Usage**: every API call writes an `llm_usage` row, regenerations included.

## 9. Frontend

- One page, `App.tsx`: an access gate (code in `sessionStorage`), then `GameInput` (Elo, color, playstyle, PGN), a progress bar, and the result headline (accuracy, counts), the `Synopsis` (react-markdown), the `ChatPanel`, and `EngineStats`.
- `analysis/pipeline.ts::runAnalysis` does create → engine-config → scan all → submit → verify → submit, with progress. `analysis/chat.ts::askCoach` loops over `engine_request` events running the deep tier.
- `api/client.ts` is a typed fetch wrapper that adds `X-Access-Code`; `api/sse.ts` reads SSE over fetch. TS types mirror the backend by hand.
- No board, no router, no chess library in the browser.
- E2E (`e2e/analysis.spec.ts`) runs the **real** Stockfish in system Chrome on an owner game. The coach is optional (`E2E_COACH=1`).

## 10. Differences from SPEC.md — summary

| SPEC | As built | Why |
|---|---|---|
| §4.2 access header, 401 | As spec; empty code disables the gate | Dev convenience |
| §5.3 scan returns "best move + eval" | Scan keeps 1 ply of PV | Spec-consistent; matters for v2 (mainline positions mostly lack multi-line results) |
| §5.4 posted evals | White-POV in the browser (Q4); backend validates legality and FEN membership | — |
| §6.1 mate → ±1 | ±1, with cp clamped to ±1000 | Q9/Q10 |
| §6.1 accuracy = mean | Lichess volatility/harmonic formula | Q11 |
| §6.1 missed mate | Plus "win% after < 90" | M3 review |
| §6.4 eight detectors | Nine (`allowed_tactic`) | M3 review |
| §6.5 key moments | Adds `line_after_san`; up to 8 | M3 review |
| §7.2 payload per call | Annotated movetext; trimmed lines; chat turns carry no game data (it's in the cached system block) | Q25/Q28, cost review |
| §7.3 never calculate | The coach may reason about plans; moves and evals stay the engine's | Commit `1e85820` |
| §7.4 validate | Buffer then send; regenerate once; strip | Q22 |
| §8 chat response | Always SSE | Q26 |
| §9 API | `+GET /api/engine-config`; 429s for daily cap and chat cap | Q5, Q27 |
| §9.1 DB | `create_all`; per-game profile | Q12 |
| §2 "up to 5 test users" | One shared code; 10 games/day server-wide | Q27 |

## 11. What v2 can reuse directly

- **Engine**: `search.ts`, `StockfishEngine` (queue), `runner.ts`, `score.ts`, `uci.ts`, `FakeTransport`. Missing for v2: cancellation (`AbortSignal`) and a streaming `onInfo` callback for the live panel.
- **Backend checks**: `check_batch`/`_check_result` for tier and legality checks; `uci_line_to_san`; `best_by_fen`; `position_evaluations`.
- **Analysis**: `build_game_context` and the detectors run unchanged on a single **candidate** move if a `MoveContext` is built for it (needed for moment hints). `classify`, `winning_chances`, `for_color`, `format_eval`.
- **Coach**: `CoachClient` protocol and fakes, `system_blocks`, `render`, `coach_view`, `annotated_movetext`, `allowed_moves`/`find_invalid`/`strip_moves`, the regenerate-then-strip loop (duplicated in `service.py` and `chat.py`, worth extracting), the `analyze_position` round trip, and `build_tool_result` (its candidate classification is the same formula as SPEC_V2 §8.3 grading).
- **API**: the SSE `_events` runner (status, keepalive, render).
