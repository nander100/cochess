# CoChess — Product & Technical Spec

Status: **v1 in scope.** Sections 1–10 define v1 in detail. Section 11 is the roadmap for v2–v4 and exists only so v1's design leaves room for them.

---

## 1. Product summary

CoChess is an AI chess coach for intermediate players (1000–1800 Elo). The user pastes a game in PGN format. A chess engine (Stockfish, running in the browser) analyzes every move. Rule-based detectors written with python-chess label *what kind* of mistakes were made. An LLM coach (Claude API) turns that data into a friendly, specific synopsis and answers follow-up questions.

**Core principle:** the engine analyzes, the LLM explains. The LLM never finds moves or evaluates positions on its own.

**Coaching style:** encouraging, concrete, Socratic. The coach helps the user think rather than handing over answers. If the user asks for the best move, the coach may give it, but follows up with a question that makes the user think (e.g. "What do you think Black's best reply is?").

## 2. v1 scope

**In:**
- Single page: profile fields (Elo, color played, optional playstyle description), PGN text box, Analyze button.
- Browser-side Stockfish analysis in three tiers: scan, verify, deep-dive (§5).
- Move classification and eight theme detectors (§6).
- Coach synopsis of the whole game (§7).
- Chat panel beside the synopsis for follow-up questions about the game, including "what if I had played X?" questions answered via an on-demand deep engine analysis (§8).
- Simple access gate (shared access code) for up to 5 test users.
- Token-usage logging for every Claude call (needed for v4 credits).
- Docker Compose setup.

**Out (later versions):** interactive board, step-through of critical moments, Explain button, accounts/Google sign-in, saved history across sessions, tendency tracking across games, dashboard, arrows, payments, credits UI, mobile layout.

## 3. User flow (v1)

1. User enters the access code (once per browser session).
2. User fills in:
   - Elo (required, integer 100–3000)
   - Color played (required: White / Black)
   - Playstyle description (optional, free text, ≤ 500 chars)
   - PGN (required)
3. User clicks **Analyze**.
4. Backend validates the PGN and returns the list of positions. Invalid PGN → clear error message (which move is illegal, or "non-standard starting positions aren't supported").
5. Browser runs the **scan** pass on every position, showing a progress bar ("Analyzing move 14 of 38…").
6. Backend picks positions to **verify**; browser runs the verify pass on them (progress bar continues).
7. Backend classifies moves, runs detectors, builds the game summary.
8. Coach synopsis streams into the synopsis panel.
9. Chat panel opens on the side. User can ask questions; some trigger a deep-dive engine analysis (§8).

Target total time for a 40-move game on a mid-range laptop: under ~45 seconds before the synopsis starts streaming.

## 4. Architecture

```
Browser (React)                          Backend (FastAPI)
─────────────────                        ─────────────────
Form + PGN ──── POST /api/games ───────► validate PGN (python-chess)
          ◄──── positions[] ──────────── 
Stockfish worker: scan pass
          ──── POST .../engine/scan ───► pick positions to verify
          ◄──── verify_fens[] ───────── 
Stockfish worker: verify pass
          ──── POST .../engine/verify ─► classify, detectors, summary → DB
          ──── POST .../synopsis ──────► build payload → Claude (stream)
          ◄──── streamed synopsis ────── validate moves, log usage
Chat      ──── POST .../chat ──────────► Claude (may call analyze_position tool)
          ◄──── engine_request ──────── (if tool called)
Stockfish worker: deep pass
          ──── POST .../chat/engine_result ► tool result → Claude (stream)
          ◄──── streamed answer ────────
```

python-chess on the backend is the single source of truth for game parsing, FENs, SAN, and legality. The frontend never parses PGN itself; it only runs the engine on FENs the backend gives it.

### 4.1 Required HTTP headers

The page must be served with:
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: require-corp`

These enable `SharedArrayBuffer`, which multi-threaded Stockfish WASM needs. Set them on the Vite dev server and in production. The engine wrapper must fall back to the single-threaded build if `crossOriginIsolated` is false, and log which build is running.

### 4.2 Access gate (v1 only)

Env var `ACCESS_CODE`. Frontend sends it as a header on every request; backend rejects requests without it (401). Replaced by real auth in v4.

## 5. Engine analysis

Stockfish.js (WASM) in a Web Worker, controlled via UCI. Use the `stockfish` npm package; check its current README for build names and how to load the multi-threaded vs. single-threaded build.

### 5.1 Score normalization

UCI reports scores from the side to move. Convert once, in one function, to White's perspective:
- `cp` → `eval_cp: int` (White POV)
- `mate N` → `mate: int` (White POV; positive = White mates)

Store exactly one of `eval_cp` / `mate` per result. Display format: `+0.3`, `-2.0`, `+M3`, `-M2`.

### 5.2 Search control: "minimum time, minimum depth, hard cap"

Each search runs `go infinite`, watches `info` lines, and sends `stop` when **both** the minimum time and minimum depth are reached, or when the hard cap is hit, whichever comes first. This keeps fast machines from wasting the time budget and stops slow machines from returning shallow, unreliable results.

Record the actual depth reached and time used with every result.

### 5.3 The three tiers (all values in config)

| Tier | When | MultiPV | Min time | Min depth | Hard cap | Lines returned |
|---|---|---|---|---|---|---|
| **Scan** | Every position in the game | 1 | 250 ms | 12 | 1000 ms | best move + eval |
| **Verify** | Flagged positions (§5.5) | 4 | 1500 ms | 18 | 3000 ms | top 4 lines, truncated to 10 plies |
| **Deep-dive** | On demand from chat (§8) | 4 | 3000 ms | 22 | 8000 ms | top 4 lines, truncated to 10 plies |

Each line returned has: `moves_uci`, `moves_san` (converted by the backend with python-chess), and the eval at the root of that line.

### 5.4 Engine result schema

```json
{
  "ply": 27,
  "fen": "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
  "tier": "verify",
  "depth": 19,
  "time_ms": 1620,
  "lines": [
    { "rank": 1, "eval_cp": 35, "mate": null, "moves_uci": ["f3g5", "d7d5", "..."] }
  ]
}
```

`fen` is the position **before** the move at `ply`. The eval of the move actually played is the eval of the position at `ply + 1` (the position after it). For the final ply, analyze the final position too.

### 5.5 Choosing positions to verify

After the scan pass, the backend flags:
1. Every **user** move whose winning-chances drop (§6.1) is at or above the inaccuracy threshold.
2. The 3 largest eval swings in the game by either side (to catch missed punishments).

For each flagged ply, verify both the position before the move and the position after it. Cap at 15 flagged plies (30 positions); if more qualify, keep the largest drops. Verified results replace scan results for classification.

## 6. Classification and theme detection (backend, python-chess)

### 6.1 Win%, move classification, accuracy

Use Lichess-style formulas. Confirm the constants against Lichess's open-source code before finalizing.

- Winning chances from centipawns: `wc = 2 / (1 + exp(-0.00368208 * cp)) - 1` (range −1..1). Win% = `50 + 50 * wc`.
- Mate scores map to wc = ±1.
- For each user move: `drop = wc_before - wc_after` from the **user's** perspective.
- Classification thresholds on `drop` (configurable):
  - Inaccuracy ≥ 0.10
  - Mistake ≥ 0.20
  - Blunder ≥ 0.30
- Also flag **"missed mate"**: the position before had a forced mate for the user and the move played lost it.
- Per-move accuracy (Lichess formula, on win% 0–100): `103.1668 * exp(-0.04354 * (winpct_before - winpct_after)) - 3.1669`, clamped to 0–100. Game accuracy = mean over the user's moves.

Tune thresholds later against the owner's real games in `tests/fixtures/pgn/user/`.

### 6.2 Game phase

- **Opening:** ply ≤ 20 and the position is not yet an endgame.
- **Endgame:** total non-pawn material on the board ≤ 26 (N=3, B=3, R=5, Q=9), or no queens on the board and each side has ≤ 1 rook + 1 minor.
- **Middlegame:** everything else.

### 6.3 Detector contract

Each detector is a pure function in `app/analysis/detectors/<name>.py`:

```python
def detect(ctx: MoveContext) -> list[ThemeFact]: ...
```

`MoveContext` contains: `board_before`, `board_after`, the move played, the user's color, the classification, evals before and after, the engine's best line from the position before, the engine's best line from the position after (the opponent's best reply), the game phase, and clock info if present.

`ThemeFact` schema:

```json
{
  "theme": "hung_piece",
  "ply": 27,
  "move_number": 14,
  "move_san": "Nd4",
  "severity": "blunder",
  "eval_before": "+0.4",
  "eval_after": "-2.6",
  "details": { "piece": "knight", "square": "d4", "lost_to": "Qxd4" }
}
```

**Rule:** per-move detectors only fire on moves classified inaccuracy or worse. Game-level detectors (development, structure summary, time trouble) produce one summary fact per game.

### 6.4 The eight v1 detectors

1. **`hung_piece`** — After the user's move, a user piece (not the king) is attacked and is either undefended or attacked by a lower-value piece, **and** the opponent's best reply (engine line from the position after) wins that piece or wins material ≥ 2 within its first 3 plies. Details: piece, square, the capturing move.

2. **`missed_capture_or_check`** — The engine's best move from the position before was a capture or check, the user played neither, and the move is a mistake or worse. Details: the best move, whether it was a capture or check, and the material won along the best line (if any).

3. **`missed_tactic`** — The engine's best line from the position before wins ≥ 2 points of material (or forces mate) within 5 plies, and the user's move does not. Tag the subtype when identifiable:
   - `fork`: the piece moved in the best move attacks ≥ 2 opponent pieces worth ≥ its value or undefended, or the king plus a piece.
   - `pin` / `skewer`: python-chess `is_pinned` / x-ray along the line through the attacked piece.
   - `discovered_attack`: the best move uncovers an attack from a line piece.
   - `back_rank`: the line delivers mate or wins material via the back rank.
   - Otherwise `combination`.
   Details: subtype, best move, material won.

4. **`slow_development`** (game-level) — At the user's 10th move: count user minor pieces still on their starting squares, and whether the user has castled. Flag if ≥ 2 minors are undeveloped, or if the user hasn't castled by their 12th move while queens are on the board. Severity raised if the user lost ≥ 0.15 wc during the opening phase. Details: undeveloped pieces, castled (y/n, which side, on which move).

5. **`king_safety`** — On a mistake or worse, where either (a) the user's move was a pawn move within the king's pawn shield (files adjacent to the king, 1–2 ranks in front), or opened a file next to the king, or (b) the opponent's best reply line contains a check within its first 3 plies and the eval drop came from an attack on the king. Details: which pawn moved or file opened, and the check sequence.

6. **`pawn_structure`** — Compare the user's pawn structure before and after the move. Flag if the move created a new doubled, isolated, or backward pawn for the user, **and** the move is an inaccuracy or worse. Also produce a game-level summary of the user's pawn structure at the end of the opening (count of doubled/isolated/passed pawns). Details: weakness type, file(s).

7. **`endgame_technique`** — On mistakes or worse during the endgame phase. Subtypes:
   - `threw_win`: user win% went from ≥ 70 to ≤ 55.
   - `passive_king`: the user's king is ≥ 3 squares from the center while the best move was a king move.
   - `allowed_passer`: the opponent gets a new passed pawn after the user's move.
   Details: subtype.

8. **`time_trouble`** (game-level) — Only if the PGN has `%clk` comments. Low clock = ≤ 10% of base time from the `TimeControl` header, or ≤ 30 s if the header is missing. Report the share of the user's mistakes and blunders made with a low clock vs. overall, and the move where low-clock play started. Details: counts and percentages.

Each detector needs unit tests with hand-built FENs: at least one position where it must fire and one where it must not.

### 6.5 Game summary (stored in DB, sent to the coach)

```json
{
  "game": { "white": "...", "black": "...", "result": "0-1", "time_control": "600+5", "opening": "ECO/opening name from PGN headers if present", "num_moves": 38 },
  "user": { "color": "white", "elo": 1350, "playstyle": "aggressive, likes 1.d4" },
  "accuracy": { "user": 78.4, "opponent": 84.1 },
  "counts": { "inaccuracies": 4, "mistakes": 2, "blunders": 1, "missed_mates": 0 },
  "phase_breakdown": { "opening": { "accuracy": 71.0, "mistakes": 2 }, "middlegame": {}, "endgame": {} },
  "eval_curve": [ { "ply": 1, "eval": "+0.2" } ],
  "key_moments": [
    {
      "ply": 27, "move_number": 14, "side": "white", "move_san": "Nd4",
      "classification": "blunder",
      "eval_before": "+0.4", "eval_after": "-2.6",
      "best_move_san": "Be3",
      "engine_lines": [ { "rank": 1, "eval": "+0.4", "moves_san": ["Be3", "..."] } ],
      "themes": ["hung_piece"]
    }
  ],
  "theme_facts": [ ],
  "move_list": [ { "ply": 1, "move_number": 1, "side": "white", "san": "d4", "eval_after": "+0.2", "classification": null } ]
}
```

`key_moments` = the user's verified mistakes/blunders/missed mates plus the 3 biggest swings, up to 8 entries, each with its verified top-4 lines (10 plies).

## 7. The coach (Claude API)

### 7.1 Models and calls

- Two configurable models: `COACH_MODEL_SYNOPSIS` (stronger) and `COACH_MODEL_CHAT` (can be cheaper). Check current model IDs in Anthropic's docs.
- Stream all responses to the frontend.
- Put the system prompt in a cache-able block (prompt caching) since it's identical across calls.
- Log every call to `llm_usage`: game id, endpoint, model, input/output tokens, cache read/write tokens, timestamp.

### 7.2 Payload sent to the coach

Every coach call sends a JSON object as the user turn's content (wrapped in a short instruction line):

```json
{
  "task": "synopsis | chat",
  "user_prompt": "what if I take on e5? I think it lets me be more active and win material",
  "player": {
    "elo": 1350,
    "color": "white",
    "rating_band": "intermediate",
    "playstyle": "aggressive, plays 1.d4",
    "tendencies": []
  },
  "pgn_to_move": "1. d4 d5 2. Bf4 ...",
  "fen": "current position FEN, if the question is about a position",
  "engine_lines": [ { "rank": 1, "eval": "+0.4", "moves_san": ["..."] } ],
  "game_summary": { }
}
```

- `rating_band`: < 1000 beginner, 1000–1800 intermediate, > 1800 advanced.
- `tendencies` is empty in v1 (cross-game tracking is v2). Keep the field so the schema doesn't change later.
- For `synopsis`, `pgn_to_move` is the full game and `fen`/`engine_lines` are omitted; `game_summary` carries everything.

### 7.3 System prompt (draft — store in `app/coach/prompts/coach_system.md`)

```
You are CoChess, a friendly, expert chess coach for club players.

Your job is to EXPLAIN analysis that a chess engine and rule-based detectors have already done. You are given that analysis as JSON.

Hard rules:
- Never calculate, guess, or propose moves yourself. Only mention moves that appear in the JSON you were given (the game's moves or the engine lines).
- Never state an evaluation that isn't in the data. Quote evals in the given format (+0.3, -2.0, +M3) and also say what they mean in words ("White is clearly better").
- If the data doesn't answer the user's question, say so, and use the analyze_position tool if a new engine analysis would answer it.
- Never invent specific puzzles, courses, books, or links. To recommend practice, name puzzle themes from this list only: fork, pin, skewer, discoveredAttack, hangingPiece, backRankMate, mateIn1, mateIn2, kingsideAttack, defensiveMove, endgame, pawnEndgame, rookEndgame, opening. Tell the user they can practice these themes in Lichess's puzzle trainer.
- For openings, you may name a well-known opening system that fits the player's first moves and level, but don't recite move-by-move lines that aren't in the data.

Coaching style:
- Match the player's level (rating_band). Beginners: simple words, one or two big ideas. Intermediate: name the concept (e.g. "isolated pawn", "loose piece") and explain why it matters. Advanced: be more concise and technical.
- Be encouraging and specific. Start with something the player did well, then the most important problems, then what to work on.
- Be Socratic. Help the player think. If they ask for the best move, you may give it, but follow up with a question that makes them think about the position (e.g. "What do you think Black's best reply is?").
- When evaluating the player's own idea, acknowledge the reasoning, then explain what the engine shows happens next.
- Use the player's playstyle description to personalize advice.

Synopsis format (task = synopsis), ~200–350 words, markdown:
1. Overall (2–3 sentences)
2. What went well
3. Key moments (2–3, each with move number, the move, evals before/after, and what went wrong)
4. What to work on (1–2 focus areas + puzzle themes to practice)
5. A closing question that invites the player to dig deeper in chat
```

### 7.4 Move-mention validation

After a full response is generated (buffer it server-side and stream to the client only once validated, or stream and append a correction if validation fails — pick one and confirm at the checkpoint):
- Extract every SAN-looking token from the response (regex for SAN: pieces, captures, squares, castling, promotions, check/mate signs).
- Each must appear in the payload's game moves or engine lines (or a tool result from this conversation).
- If any don't: regenerate once with a note listing the invalid moves. If it fails again, return the response with those moves removed and log the incident.

## 8. Chat and deep-dive analysis

### 8.1 Chat context

Each chat call sends: the system prompt, the game summary, the full chat history for this game, and the new user message as a §7.2 payload with `task: "chat"`.

### 8.2 The `analyze_position` tool

Give Claude one tool:

```json
{
  "name": "analyze_position",
  "description": "Ask the chess engine to analyze a position from this game, optionally after a candidate move the player suggests. Use when the user asks about a move or idea not covered by the analysis you already have.",
  "input_schema": {
    "type": "object",
    "properties": {
      "ply": { "type": "integer", "description": "Analyze the position before this ply (1 = White's first move)." },
      "candidate_move_san": { "type": "string", "description": "Optional move the player is asking about, in SAN." }
    },
    "required": ["ply"]
  }
}
```

The payload's `move_list` includes ply numbers so Claude can map "move 14" + side to a ply.

### 8.3 Round-trip flow (engine runs in the browser)

1. Claude calls `analyze_position`.
2. Backend validates: ply in range; `candidate_move_san` legal in that position (python-chess). If illegal, return a tool error to Claude ("Nxe5 is not legal here") and let it answer.
3. Backend pauses the conversation, saves the pending tool call, and responds to the frontend with `{ "type": "engine_request", "request_id", "positions": [fen_before, fen_after_candidate?] }`.
4. Frontend shows "Coach is thinking deeply…" and runs the **deep-dive** tier (§5.3) on each position.
5. Frontend posts results to `/chat/engine_result`.
6. Backend converts lines to SAN, builds a tool result (eval before, eval after the candidate, top 4 lines at 10 plies, and the difference vs. the best move), and resumes the Claude conversation; the answer streams back.

Limit: at most 2 tool calls per user message.

## 9. Backend API (v1)

| Method & path | Body | Returns |
|---|---|---|
| `POST /api/games` | `{ pgn, user_color, elo, playstyle? }` | `{ game_id, positions: [{ ply, fen_before, san, uci, clock_s? }], final_fen }` or 422 with a clear error |
| `POST /api/games/{id}/engine/scan` | `{ results: EngineResult[] }` | `{ verify_fens: [ ... ] }` |
| `POST /api/games/{id}/engine/verify` | `{ results: EngineResult[] }` | `{ summary_ready: true, counts, accuracy }` |
| `POST /api/games/{id}/synopsis` | — | streamed text (SSE) |
| `POST /api/games/{id}/chat` | `{ message }` | streamed text (SSE), or `{ type: "engine_request", ... }` |
| `POST /api/games/{id}/chat/engine_result` | `{ request_id, results: EngineResult[] }` | streamed text (SSE) |
| `GET /api/health` | — | `{ ok: true }` |

### 9.1 Database (SQLite, v1)

- `games` (id, pgn, user_color, elo, playstyle, headers JSON, created_at)
- `engine_results` (game_id, ply/fen, tier, depth, time_ms, lines JSON)
- `game_summaries` (game_id, summary JSON)
- `chat_messages` (game_id, role, content JSON, created_at)
- `pending_tool_calls` (request_id, game_id, tool_use JSON, created_at)
- `llm_usage` (game_id, endpoint, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, created_at)

Design schemas so a `user_id` column can be added in v2 without breaking anything.

### 9.2 PGN rules

- Parse with python-chess. Use the main line only; strip variations, comments, and NAGs, but keep `%clk` values.
- Reject: no moves, illegal moves (report the move number), `SetUp`/`FEN` headers with a non-standard position, `Variant` header other than standard.
- Accept multiple games in one paste? **No** — v1 accepts exactly one game; reject with a clear message otherwise.

## 10. v1 milestones and checkpoints

Stop for owner review at every ✅ checkpoint (see CLAUDE.md).

- **M0 — Plan & scaffold.** Read CLAUDE.md and this spec, write an implementation plan, list any open questions. Scaffold backend and frontend, Docker Compose, lint/test/typecheck all passing on empty projects, COOP/COEP headers set. ✅ *Checkpoint: plan + scaffold.*
- **M1 — PGN ingestion.** `POST /api/games`, validation rules, tests. Owner adds 5 real games to `tests/fixtures/pgn/user/`.
- **M2 — Browser engine.** Stockfish worker wrapper with the three tiers and the min-time/min-depth/hard-cap logic, multi-threaded with single-threaded fallback, progress reporting. Scan and verify endpoints. ✅ *Checkpoint: show depth/time stats and evals for one real fixture game.*
- **M3 — Classification & detectors.** Win%, classification, accuracy, game phase, all eight detectors with unit tests, game summary builder. ✅ *Checkpoint: print the game summary JSON for 3 real fixture games for the owner to sanity-check as a chess player.*
- **M4 — Coach synopsis.** Payload builder, system prompt file, Anthropic client with streaming, caching, usage logging, move validation. ✅ *Checkpoint: 3 real synopses (one per rating band, by changing the Elo field) for review.*
- **M5 — Chat & deep-dive.** Chat endpoint, `analyze_position` tool round-trip, deep tier, frontend chat panel. ✅ *Checkpoint: demo a "what if I play X?" conversation on a fixture game.*
- **M6 — Ship v1.** Access gate, error states, README with setup steps, production build, deploy instructions for a single small server. ✅ *Checkpoint: final review.*

**v1 is done when:** the owner agrees with the synopsis on 5 of their own games, no coach response contains a move that isn't in the data, and all tests, lint, and type checks pass.

---

## 11. Roadmap (do not build in v1)

### v2 — Critical moments and Socratic step-through
- Interactive chessground board with move navigation and an eval graph (click to jump).
- Step through critical moments like Lichess computer analysis: board jumps to the position before each mistake, coach asks "What would you play here and why?", user answers in chat or on the board, engine evaluates their idea, coach reveals and explains.
- Full §7.2 payload sent with every chat message, using the board's current position; exploring variations on the board updates `fen`, `pgn_to_move`, and `engine_lines`.
- "Explain" button: summarize what has happened so far and the plan going forward (answers in the chat panel).
- Basic accounts so data persists, cross-game tendency tracking with recency weighting (e.g. exponential decay, weight halves every 10 games), stored per theme.
- 12-game onboarding assessment: 6 as White, 6 as Black, including 3 wins and 3 losses per color, in the user's main time control → baseline report.
- Editable playstyle description in the profile.

### v3 — Polish and richer coaching
- Coach can return structured annotations (`{"arrows": [["e4","d5","green"]], "highlights": ["f7"]}`), validated against engine lines, drawn on the board.
- Step through recommended lines move by move with explanations.
- Dashboard: top focus areas, common mistake types over time, accuracy trend, recent games.
- Puzzle-theme recommendations linked directly to Lichess puzzle themes.
- UI polish, loading states, keyboard navigation.
- Optional: import games from Lichess / Chess.com by username.

### v4 — Production
- Google sign-in (OAuth).
- Stripe subscriptions (e.g. $10/month including a monthly API credit allowance) and one-time credit top-ups.
- Credit metering from `llm_usage` (token counts × current model pricing), usage tracker in the UI, block or warn at zero.
- Cost controls: prompt caching, model routing, compact payloads.
- **Credit budget (owner decision, post-v1 cost review):** a $10/month subscription includes at most **$3/month of API usage** per user. At the v1 defaults (Sonnet 5.5 low-effort synopsis, Haiku 5.5 chat, ~$0.02 per game with a few questions) that is roughly 150 analyzed games a month.
- **User-selectable coach strength:** users can raise the coach to a stronger model and effort (e.g. Opus synopsis, Sonnet chat, ~$0.08 per game) for more in-depth analysis. The UI must say that it uses their allotted credits faster (roughly 4× at those settings, about 35–40 games a month on the $3 allowance). Model and effort are already per-call settings in `CoachSettings`, so this means making them per-user instead of per-server.
- Deployment on AWS (App Runner or ECS, RDS Postgres, Secrets Manager), monitoring, backups, rate limiting.
- Terms of service, privacy policy, account deletion.
- Later: Chessly-style opening courses and drills.
