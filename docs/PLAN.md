# CoChess v1 — Implementation Plan (M0)

Status: **approved 2026-10-25.** Owner installed uv, upgraded Node (v24), approved all listed
dependencies, and asked for no `git push` until v1 is complete. Recommendations in §5 are the
working defaults unless overridden. Change from the draft: the Vite template now ships `oxlint`,
which replaces ESLint (`npm run lint`).
Sources: `CLAUDE.md`, `SPEC.md` §1–§10. v2–v4 (§11) are only design constraints.

---

## 0. Verified facts (checked 2026-10-25, not assumed)

| Item | What I found | Source |
|---|---|---|
| `stockfish` npm | Latest `19.0.1` (Stockfish 19). Files in `bin/`: `stockfish-19.js/.wasm` (multi-threaded, **99 MB wasm**), `stockfish-19-single.js/.wasm` (single, **99 MB**), `stockfish-19-lite.js/.wasm` (multi, **1.7 MB**), `stockfish-19-lite-single.js/.wasm` (single, **1.8 MB**), `stockfish-19-asm.js`. Loaded as `new Worker("<file>.js")`; the `.wasm` must sit next to its `.js`; served as `application/wasm`. Multi-threaded builds need COOP/COEP. | npm tarball + package README |
| Lichess win% | `wc = 2 / (1 + exp(-0.00368208 * cp)) - 1`, matches spec. **But** cp is clamped to ±1000 first (`Cp.ceiled`), and mate maps to ±1000 cp (≈ wc ±0.95), not ±1. | `scalachess` `eval.scala` |
| Lichess accuracy | `103.1668100711649 * exp(-0.04354415386753951 * diff) - 3.166924740191411`, **plus a +1 "uncertainty bonus"**, clamped 0–100; 100 if win% didn't drop. Game accuracy is **not** a simple mean: it's `(volatility-weighted mean + harmonic mean) / 2`, window size `clamp((n-1)/10, 2, 8)`, weights = window stdev clamped 0.5–12. | `lila` `AccuracyPercent.scala` |
| Claude models | Current: `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. Adaptive thinking is on by default. | platform.claude.com models overview |
| Prompt caching | `system=[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]` (5 min; `"ttl":"1h"` optional). Min cacheable prefix 512 tokens on all 5.x models. Usage fields: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. | platform.claude.com prompt-caching |
| Local toolchain | `uv` **not installed**. Node **18.19** (EOL). Vite 7 needs Node ≥20.19; Vite 6.4 / Vitest 3 still support Node 18. Python 3.12.3, Docker present. Latest: `anthropic` 2.3.0, `chess` 1.11.2, `fastapi` 0.162.0, React 19.3. | local shell, npm/PyPI |

---

## 1. Architecture recap

Follows SPEC §4 exactly: backend owns parsing, SAN, legality, classification, detectors, summary and all Claude calls; the browser only runs Stockfish on FENs the backend hands it. The LLM only receives JSON built from engine + detector output; every SAN token it emits is checked against that JSON.

---

## 2. Backend design

### 2.1 Modules and main interfaces

```
app/config.py           Settings (pydantic-settings): ACCESS_CODE, ANTHROPIC_API_KEY,
                        COACH_MODEL_SYNOPSIS, COACH_MODEL_CHAT, DATABASE_URL,
                        EngineTiers (scan/verify/deep), Thresholds (§6.1), limits.
app/main.py             create_app(); middleware: access gate (X-Access-Code, hmac.compare_digest,
                        /api/health exempt), COOP/COEP headers; routers.
app/api/games.py        POST /api/games, /engine/scan, /engine/verify, GET /api/engine-config
app/api/coach.py        POST /synopsis, /chat, /chat/engine_result (SSE)

app/analysis/pgn.py
    parse_pgn(text: str) -> ParsedGame                    # raises PgnError(code, message, move_number?)
app/analysis/evals.py
    to_white_pov(...)                                      # see Q4 — the single conversion point
    Eval (cp | mate, exactly one) ; format_eval(Eval) -> "+0.3" | "-M2"
    winning_chances(Eval) -> float ; win_pct(Eval) -> float
    move_accuracy(wp_before, wp_after) -> float ; game_accuracy(win_pcts, color) -> float
    classify(drop, mate_before, mate_after) -> Classification | None
app/analysis/material.py
    material(board, color) -> int ; material_delta_along_line(board, uci_moves, plies, pov) -> int
    uci_line_to_san(fen, uci_moves, max_plies=10) -> list[str]   # stops at first illegal move
app/analysis/selection.py
    select_verify_plies(scan_evals, user_color, cfg) -> list[int]   # §5.5
app/analysis/phase.py
    game_phase(board, ply) -> Phase
app/analysis/detectors/__init__.py
    PER_MOVE: list[Callable[[MoveContext], list[ThemeFact]]]
    GAME_LEVEL: list[Callable[[GameContext], list[ThemeFact]]]
app/analysis/detectors/{hung_piece,missed_capture_or_check,missed_tactic,slow_development,
                        king_safety,pawn_structure,endgame_technique,time_trouble}.py
app/analysis/summary.py
    build_summary(game: ParsedGame, profile, results: dict[fen, EngineResult]) -> GameSummary

app/coach/payload.py    build_synopsis_payload(summary, game) / build_chat_payload(...) -> CoachPayload
app/coach/prompts/coach_system.md
app/coach/client.py     CoachClient(Protocol) + AnthropicCoachClient(AsyncAnthropic): streaming,
                        cache_control on system, usage -> llm_usage. Tests inject a fake.
app/coach/validate.py   extract_san_tokens(text) -> list[str] ; allowed_moves(payload, tool_results) -> set[str]
                        find_invalid(text, allowed) -> list[str] ; strip_moves(text, invalid) -> str
app/coach/service.py    run_synopsis(game_id) / run_chat(game_id, msg) / resume_chat(request_id, results)
                        — orchestrates regenerate-once, tool loop (≤2 tool calls/message), SSE events.
app/db/models.py, app/db/session.py
```

All detectors are pure; `MoveContext`/`GameContext` are frozen dataclasses (they hold `chess.Board`, which Pydantic can't model cleanly). Everything that crosses an API or goes to Claude is a Pydantic v2 model.

### 2.2 Core Pydantic schemas

```python
class Position(BaseModel):          # POST /api/games response item
    ply: int; fen_before: str; san: str; uci: str; clock_s: float | None
class EngineLine(BaseModel):
    rank: int; eval_cp: int | None; mate: int | None; moves_uci: list[str]   # White POV
class EngineResult(BaseModel):      # §5.4, validated: exactly one of eval_cp/mate per line
    ply: int | None; fen: str; tier: Literal["scan","verify","deep"]; depth: int; time_ms: int
    lines: list[EngineLine]
class ThemeFact(BaseModel):         # §6.3; ply/move_number/move_san None for game-level facts
    theme: ThemeName; ply: int | None; move_number: int | None; move_san: str | None
    severity: Severity; eval_before: str | None; eval_after: str | None; details: dict[str, str|int|float|bool|list[str]|None]
class GameSummary(BaseModel): ...   # §6.5 field-for-field (GameInfo, UserInfo, Accuracy, Counts,
                                    # PhaseBreakdown, EvalPoint, KeyMoment, MoveEntry)
class CoachPayload(BaseModel): ...  # §7.2 field-for-field; tendencies: list[str] = []
```

Backend rejects engine results whose FEN it didn't hand out for that game/tier (no arbitrary FENs stored), and validates every UCI move with python-chess when converting to SAN.

### 2.3 Database (SQLAlchemy 2.0, SQLite)

| Table | Columns | Notes |
|---|---|---|
| `games` | id (uuid str PK), pgn, user_color, elo, playstyle, headers JSON, created_at | `user_id` nullable column added in v2 |
| `engine_results` | id, game_id FK, ply nullable, fen, tier, depth, time_ms, lines JSON, created_at | unique (game_id, fen, tier); classification uses the highest tier per FEN |
| `game_summaries` | game_id PK/FK, summary JSON, created_at | |
| `chat_messages` | id, game_id FK, role, content JSON, created_at | content = Anthropic content blocks, verbatim (thinking + tool_use blocks preserved for replay) |
| `pending_tool_calls` | request_id PK, game_id FK, tool_use JSON, assistant_content JSON, positions JSON, tool_calls_used, created_at | |
| `llm_usage` | id, game_id FK nullable, endpoint, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, created_at | |

Schema created with `Base.metadata.create_all` in v1 (see Q12).

### 2.4 API surface

SPEC §9 as written, plus `GET /api/engine-config` (Q5). All coach endpoints return SSE with typed events: `text` (chunk), `engine_request` (`{request_id, positions:[{fen, label}]}`), `done` (`{invalid_moves_removed: n}`), `error` (Q26).

---

## 3. Frontend design

```
src/engine/uci.ts          parseInfoLine(line) -> {depth, multipv, score, pv} ; pure, unit-tested
src/engine/score.ts        toWhitePov(fen, score)                      (if Q4 = frontend)
src/engine/StockfishEngine.ts
    class StockfishEngine { static create(): Promise<StockfishEngine>   // picks lite vs lite-single by crossOriginIsolated, logs build
                            analyze(fen, tier: TierConfig, signal?): Promise<EngineResult> }
                            // go infinite; stop when (elapsed ≥ minTime && depth ≥ minDepth) || elapsed ≥ hardCap
src/engine/runner.ts       runBatch(engine, fens, tier, onProgress) -> EngineResult[]
src/api/client.ts          typed fetch wrapper (adds X-Access-Code), SSE reader over fetch ReadableStream
src/api/types.ts           TS mirrors of backend schemas
src/components/AccessGate.tsx, GameInput.tsx, ProgressBar.tsx, Synopsis.tsx, ChatPanel.tsx
src/App.tsx                state machine: gate → input → scanning → verifying → synopsis+chat
```

The search controller is written against an `EngineTransport` interface (`send(cmd)`, `onLine(cb)`) so Vitest can drive it with a fake engine and fake timers. Stockfish files are copied from `node_modules/stockfish/bin` into `public/engine/` by a `postinstall` script (not committed). Vite dev server and production server send COOP/COEP.

---

## 4. Milestones (each step = one commit, tests alongside)

**M0 — Plan & scaffold** ✅ checkpoint
1. This plan → approval.
2. `backend/`: uv project, FastAPI app with `/api/health`, COOP/COEP middleware, config, ruff/mypy/pytest config, one passing test.
3. `frontend/`: Vite + React + TS, ESLint, Vitest, COOP/COEP in `vite.config.ts`, one passing test.
4. `docker-compose.yml` (backend + frontend; frontend served by nginx in prod with COOP/COEP + wasm MIME, proxying `/api`), `.gitignore`, `.env.example`.
5. Evidence: all five commands green, `curl -I` showing headers, `crossOriginIsolated === true` in browser.

**M1 — PGN ingestion**
- `pgn.py` + `POST /api/games` + `games` table. Tests: valid game, illegal move (reports move number), `SetUp`/`FEN` non-standard → rejected, `FEN` = standard start → accepted, Chess960 `Variant` → rejected, multiple games → rejected, empty/no moves → rejected, variations/comments/NAGs stripped, `%clk` preserved, size/ply limits.
- Owner adds 5 games to `backend/tests/fixtures/pgn/user/`. (No checkpoint — I'll ask for the games and continue.)

**M2 — Browser engine** ✅ checkpoint
- `uci.ts`, `score.ts`, `StockfishEngine`, `runner.ts`, ProgressBar; scan/verify endpoints, `select_verify_plies`, `engine_results` table.
- Tests: UCI parsing (cp, mate, lowerbound/upperbound lines ignored, multipv), stop logic with fake transport + fake timers (fast machine stops at min time; slow machine stops at hard cap; min depth honored), POV conversion, verify selection (threshold, top-3 swings, 15-ply cap, FEN dedupe), backend rejects unknown FENs / illegal UCI.
- Evidence: per-position depth/time table + evals for one real fixture game, total wall time, which build ran.

**M3 — Classification & detectors** ✅ checkpoint
- `evals.py`, `phase.py`, `material.py`, eight detectors, `summary.py`, `game_summaries`.
- Tests: formula values vs. hand-computed Lichess numbers; classification boundaries; missed mate; phase rules; each detector ≥1 positive and ≥1 negative hand-built FEN; summary built from canned engine results (no engine needed in pytest).
- Evidence: summary JSON for 3 real fixture games. To make this reproducible in pytest I'll save the M2 engine output for those games as JSON fixtures.

**M4 — Coach synopsis** ✅ checkpoint
- `coach_system.md`, `payload.py`, `client.py`, `validate.py`, `service.py`, `/synopsis` SSE, `llm_usage`, Synopsis component (markdown rendering).
- Tests (mocked client): payload shape & rating bands, cache_control present, usage row written, validator (SAN regex coverage, castling/promotion/check signs, allowed set), regenerate-once then strip path.
- Evidence: 3 real synopses for one game at Elo 800 / 1400 / 2000, plus token/cache usage rows.

**M5 — Chat & deep-dive** ✅ checkpoint
- `/chat`, `/chat/engine_result`, `analyze_position` tool, ply/legality validation, tool errors, ≤2 tool calls per message, deep tier in runner, ChatPanel with "Coach is thinking deeply…".
- Tests: tool input validation (bad ply, illegal candidate → tool error), pending call save/resume with thinking blocks preserved, tool limit, tool-result moves added to allowed set.
- Evidence: transcript of a "what if I play X?" conversation on a fixture game.

**M6 — Ship v1** ✅ checkpoint
- Access gate UI + middleware tests, error states (bad PGN, engine load failure, API failure, 401), README (setup, env vars, commands), production Docker build, deploy notes for one small VPS (compose + Caddy/nginx TLS).
- Evidence: fresh-clone `docker compose up --build` walk-through, all checks green.

---

## 5. Open questions & recommended changes

Each has my recommendation in **bold**. Items 1–3 block scaffolding.

**Environment**
1. **`uv` isn't installed.** **Install it** (`curl -LsSf https://astral.sh/uv/install.sh | sh`) — you run it, or OK me to.
2. **Node 18 is EOL.** **Upgrade to Node 22 LTS and use Vite 7.** Otherwise I'll pin Vite 6.4 / Vitest 3, which work on 18. Docker images use Node 22 either way.
3. **Dependencies not named in CLAUDE.md** — I need approval for:
   - Backend: `uvicorn[standard]`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (TestClient), `ruff`, `mypy`.
   - Frontend: `@vitejs/plugin-react`, `vitest`, `@testing-library/react` + `jsdom`, `eslint` + `typescript-eslint` + `eslint-plugin-react-hooks`, `react-markdown` (render the synopsis markdown safely, no raw HTML).
   - Infra: `nginx` image for serving the frontend in production.

**Engine**
4. **Where the cp→White-POV conversion happens.** §5.4 has the browser posting White-POV evals, so **do it in the frontend (`score.ts::toWhitePov`, the one place), and have the backend validate the shape only.** Alternative: browser posts raw side-to-move scores and the backend converts (changes the §5.4 schema).
5. **One source of truth for tier settings.** CLAUDE.md wants engine settings in config, but the engine runs in the browser. **Add `GET /api/engine-config`** so the frontend reads tiers from backend config instead of duplicating them.
6. **Which Stockfish build.** The full builds ship a 99 MB wasm per user; the lite builds are 1.7 MB (smaller NNUE, still far stronger than needed to judge 1000–1800 games). **Use `stockfish-19-lite` (multi-threaded) with `stockfish-19-lite-single` fallback.** Threads = `min(hardwareConcurrency − 1, 4)`, Hash 64 MB, both in config.
7. **45-second target looks tight.** A 40-move game is ~81 positions × ≥250 ms scan ≈ 20–30 s, plus up to 30 verify positions × 1.5–3 s ≈ 45–90 s worst case. **Dedupe FENs (ply N's "after" is ply N+1's "before"), measure at M2, then tune** (e.g. verify min time 1000 ms or a 10-ply cap). I'll report real numbers at the M2 checkpoint.
8. **Terminal positions** (checkmate/stalemate, e.g. the final position): Stockfish returns `mate 0` / no bestmove, and "mate 0" has no sign. **The backend computes these from python-chess (checkmate → winner's wc = +1, stalemate/draw → 0) and the frontend skips them.**

**Win% / accuracy (§6.1 vs. Lichess source)**
9. **Clamp cp to ±1000 before win%**, as Lichess does. Spec doesn't mention it.
10. Mate → wc: spec says ±1, Lichess uses ±1000 cp (≈ ±0.95). **Follow the spec (±1)**: a missed mate is caught separately by the missed-mate flag, and ±1 is cleaner. This makes accuracy differ from Lichess only marginally.
11. **Use Lichess's real accuracy formula** (+1 uncertainty bonus; game/phase accuracy = (volatility-weighted mean + harmonic mean)/2) instead of the spec's simple mean, so our numbers match what users see on Lichess. Thresholds 0.10/0.20/0.30 on wc already match Lichess.

**Persistence**
12. **No Alembic in v1**: `create_all` on startup, add Alembic when moving to Postgres in v2. (Alembic would also be a new dependency.)

**Detectors (§6.4) — interpretations to confirm**
13. `missed_tactic` "and the user's move does not": **fire when the best line wins ≥2 points (or mates) within 5 plies, the played move ≠ best move, and the move is an inaccuracy or worse.**
14. Material "within N plies": counting at an exact ply can land mid-exchange. **Measure at ply N and extend one ply if ply N was a capture (allow the recapture).**
15. `king_safety` (b) "drop came from an attack on the king" isn't directly computable. **Proxy: the opponent's reply line has a check in its first 3 plies AND (the line ends in mate OR it wins <2 material, i.e. the drop isn't just a material grab).**
16. `endgame_technique.passive_king`: **"≥3 squares from the center" = Chebyshev distance ≥3 to the nearest of d4/d5/e4/e5.**
17. `pawn_structure` game-level "end of the opening" = **the first ply whose phase isn't opening** (or the last ply if the game never leaves the opening).
18. `ThemeFact.severity` for game-level facts. Per-move facts use the move classification. **Game-level facts use `"note"`, raised to `"concern"`** (e.g. slow development with ≥0.15 wc lost in the opening).
19. `key_moments` priority when >8 candidates: **missed mates → blunders → mistakes (by drop size) → top-3 swings not already included.**
20. **Classify both sides' moves** (needed for opponent accuracy and the move list); detectors run only on user moves.
21. `missed_mate`: **fires only if the user had a forced mate before and has none after.** Mate-in-3 → mate-in-5 is not a missed mate.

**Coach**
22. **§7.4 validation: buffer server-side, validate, then send** (with a "Coach is writing…" indicator). This is the only option that guarantees the v1 done criterion "no coach response contains a move that isn't in the data". Streaming then correcting would briefly show invalid moves. Costs a few seconds before text appears.
23. **Bare squares are ambiguous in SAN validation:** "the e4 pawn" matches pawn-move SAN `e4`. **Validate tokens with a piece letter, capture, castling, promotion, or +/#, plus bare squares only when written as a move (after a move number like `14.`/`14...`).** Tell the coach in the prompt to write "the knight on f3", not "Nf3", when naming a piece. Validation is set membership (SAN normalized without +/#), not per-position.
24. **Models:** **`COACH_MODEL_SYNOPSIS=claude-opus-5-5`, `COACH_MODEL_CHAT=claude-sonnet-5-5`.** Haiku 5.5 is cheaper but I'd test it for the Socratic/tool-use chat before choosing it.
25. **Chat caching.** Per-turn payloads would resend the whole `game_summary`. **Put the game summary in a second cached system block** (stable per game), and send only `task`, `user_prompt`, `player`, plus `fen`/`engine_lines` when relevant in each chat turn. Same information, much better cache hits. Small deviation from §7.2/§8.1.
26. **One response type for `/chat`.** Spec returns SSE *or* JSON. **Always SSE, with an `engine_request` event**, so the client has one code path.
27. **Cost guard for 5 test users:** **cap at 30 chat messages per game and 10 games per access code per day, both in config, returning a clear error.** Spec is silent; the global rules ask for rate limiting.
28. Drop `eval_curve` from the coach payload (it duplicates `move_list[].eval_after`) but keep it in the DB summary? **Yes, it saves tokens on every call.**

**Repo**
29. You're on branch `EE175` with no commits and no `main` yet. **Commit milestones on `EE175`**, and you merge/PR to `main` at checkpoints. Say if you'd rather I create `main` first.
