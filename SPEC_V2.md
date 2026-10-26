# CoChess — v2 Spec

Status: **v2 in scope.** This builds on v1 (`SPEC.md`, kept as the record of what v1 was meant to be). Where this file and `SPEC.md` disagree, this file wins. Sections 1–13 define v2 (§13 is the milestone plan). Section 14 is the roadmap for v3–v4.

---

## 1. What v2 adds

v1: paste a PGN, get a whole-game synopsis, chat about it.

v2 turns CoChess into an analysis board and a coach that teaches move by move:

1. **Accounts (lightweight).** Each user has a profile and their own saved games. Invite-link login for the small test group; Google sign-in replaces it in v4.
2. **Analysis board.** Interactive chessground board, move list with mistake markers, eval graph, variations, and an optional live engine panel, laid out like Lichess analysis.
3. **Position-aware chat and an Explain button.** Every chat message carries the position on the board, including variations the user is exploring.
4. **Critical moments, taught Socratically.** Step through the game's turning points in order. The coach explains what went wrong, asks the user to find a better move, grades their attempt with the engine, gives grounded hints, then reveals.
5. **Tendency tracking.** Mistake themes aggregated across games with a heavy bias toward recent games, fed to the coach.
6. **12-game onboarding assessment** producing a baseline report.

**Core principle (unchanged):** the engine analyzes, the LLM explains.

**New principle for v2: withhold, don't instruct.** When the coach must not reveal something (the best move before the user has tried), the backend leaves it out of the payload. The prompt alone is never trusted to keep a secret.

## 2. v2 scope

**In:** everything in §1, plus a "My games" list, an editable profile, per-user usage logging, and an Alembic migration setup.

**Out (v3+):** dashboard with charts, arrows/highlights drawn by the coach, guided line stepping, links into specific puzzles, game import from Lichess/Chess.com, UI polish pass, Google sign-in, payments, credits UI, mobile layout.

Basic left/right arrow-key navigation on the board is in v2. The full keyboard-shortcut set is v3.

## 3. Step zero: reconcile with v1 as built

v1 may have drifted from `SPEC.md` during implementation. Before planning v2, Claude Code must:
1. Read the codebase and compare it to `SPEC.md`.
2. Write `docs/v1-as-built.md`: actual endpoints, schemas, payload shapes, engine settings, detector behavior, and anything that differs from the spec.
3. Adjust this plan to fit the real code, and list the adjustments at the M0 checkpoint.

Reuse v1 pieces wherever they fit: the engine worker and its fake transport for tests, the detectors, the payload builder, move validation, and the `analyze_position` round trip.

## 4. Accounts and profiles

### 4.1 Login: invite links (v2 only)

No passwords in v2. The owner creates users from the command line:

```
uv run python -m app.cli create-user --name "Alex"
uv run python -m app.cli invite --user Alex      # prints a one-time login link
```

- The link contains a random token (≥ 32 bytes, URL-safe). Only its hash is stored. It works once and expires after 7 days.
- Opening the link calls `POST /api/auth/redeem`, which creates a server-side session and sets an `httpOnly`, `Secure` (in production), `SameSite=Lax` cookie. Sessions last 30 days.
- Lost cookie → owner issues a new invite.
- The v1 shared access code is removed.
- Keep auth in its own module behind a small interface (`get_current_user`) so Google OAuth can replace invites in v4 without touching the rest of the app.

### 4.2 Data isolation

Every query on user data is scoped by `user_id`. A user requesting another user's game gets 404. Write a test for this on every user-data endpoint.

Engine results come from the user's browser, so they are untrusted. Cache and reuse them only within the same user's data, never across users.

### 4.3 Profile

Fields: display name, Elo (100–3000), primary time control (bullet / blitz / rapid / classical), playstyle description (≤ 500 chars). Editable any time on a Profile page. Each game stores the Elo the user had when it was analyzed.

### 4.4 Migrating v1 data

Add Alembic with a baseline migration that matches the current v1 schema, then migrations for v2. Provide a CLI command to assign all existing v1 games to a given user (the owner).

## 5. Analysis board

### 5.1 Layout (desktop only)

```
┌───────────────────────────┬──────────────────────────────┐
│ [eval bar] [  board  ]    │ Tabs: Moves | Moments        │
│                           │ (move list or moment stepper)│
│ [ eval graph            ] ├──────────────────────────────┤
│ [ engine panel (toggle) ] │ [Explain]                    │
│                           │ Chat                         │
└───────────────────────────┴──────────────────────────────┘
```

Opening a game from "My games" loads everything from the database: moves, evals, classifications, critical moments, synopsis, and chat history. Nothing is re-analyzed.

### 5.2 Board and game tree

- **chessground** for the board; **chess.js** in the browser for legal-move destinations and building SAN while the user explores.
- The frontend keeps a game tree: the mainline plus any variations the user plays. Each node has `fen`, `san`, `uci`, `parent`, and `children`.
- The current position is identified by its **path**: the list of UCI moves from the start position. That path is what the frontend sends to the backend.
- The backend replays the path with python-chess to get the FEN, SAN, and PGN. It never trusts a FEN or SAN string supplied by the client. python-chess on the backend remains the source of truth for everything sent to Claude.
- Variations are kept for the browser session. Saving them is v3.

### 5.3 Move list

- Mainline moves with glyphs on the user's moves: `?!` inaccuracy, `?` mistake, `??` blunder, and a marker for missed mates.
- Variations shown inline and indented, like Lichess.
- Click any move to jump. ← and → step back and forward.

### 5.4 Eval graph

- Plot win% from White's point of view (§6.1 of `SPEC.md`), not raw centipawns, so the graph doesn't spike to ±M.
- Hover shows the eval in display format (`+1.2`, `-M3`). Click jumps to that move.
- Colored dots on the user's inaccuracies, mistakes, and blunders.
- Build it as a plain SVG React component. No chart library.

### 5.5 Live engine panel

- Toggle (off by default). Shows an eval bar and the top lines for the current position.
- Runs the browser engine continuously on the displayed position (`go infinite`, MultiPV 3), stops when the position changes, and stops after 10 seconds on the same position.
- **Hidden and disabled during an unsolved critical moment** (§8), so the user can't peek.

## 6. Position-aware chat and Explain

### 6.1 Coach payload v2

Every coach call sends this JSON (extends `SPEC.md` §7.2):

```json
{
  "task": "synopsis | chat | explain | moment_intro | moment_feedback | baseline_report",
  "user_prompt": "what if I take on e5?",
  "player": {
    "elo": 1350,
    "color": "white",
    "rating_band": "intermediate",
    "playstyle": "aggressive, plays 1.d4",
    "tendencies": [ ]
  },
  "position": {
    "path_san": ["d4", "d5", "Bf4", "..."],
    "pgn_to_move": "1. d4 d5 2. Bf4 ...",
    "fen": "...",
    "ply": 23,
    "on_mainline": false,
    "branch_ply": 21,
    "variation_san": ["Nxe5", "Nxe5", "dxe5"]
  },
  "engine_lines": [ { "rank": 1, "eval": "+0.4", "moves_san": ["..."] } ],
  "game_summary": { },
  "moment": null
}
```

- `tendencies` is now filled in (§9.3).
- `position` describes what's on the board. If the user branched off the game, `branch_ply` is where they left the mainline and `variation_san` is what they played since.
- `engine_lines`: top 4 lines, 10 plies, for the current position (verify tier from `SPEC.md` §5.3). Mainline positions usually already have these stored; if not, or if the position is in a variation, the frontend runs the verify tier first and sends the result with the request. The backend checks the result's FEN matches the replayed path.
- `moment` is only used for moment tasks (§8). For moment tasks before reveal, `engine_lines` for the moment's position is filtered as §8.4 describes.

### 6.2 Chat

- Each message sends `{ message, path_uci, engine_result? }`. Each stored chat message records the path it was sent from.
- The `analyze_position` tool from v1 is updated: `ply` becomes optional (default = the current board position), and `candidate_move_san` becomes `candidate_moves_san`, a list of up to 3 plies so the user can ask about short sequences ("what if I take on e5 and he recaptures with the knight?"). The v1 browser round trip is otherwise unchanged.

### 6.3 Explain button

- Sends `task: "explain"` for the current position.
- The coach covers (a) what has happened so far, using the eval curve and key moments up to this ply, and (b) the best course forward, described as plans drawn from the engine lines ("White wants to push the c-pawn and attack the queenside"). The answer appears in the chat panel.
- In a variation, the coach also compares the variation to what happened in the game.
- Disabled during an unsolved critical moment.

### 6.4 Prompt caching

Put the system prompt and the game summary in cached blocks ahead of the conversation. They repeat on every call for a game, so caching both cuts cost noticeably.

## 7. System prompt updates

Keep the v1 system prompt and add these sections. Store prompts as files in `app/coach/prompts/`, one per task where the instructions differ.

- **Position awareness:** "The `position` object is what the player sees on the board right now. Talk about that position. If `on_mainline` is false, the player is exploring their own idea; say how it compares to the game."
- **Explain:** structure (what happened → where things stand, with the eval in words → the plan going forward) in about 120–200 words.
- **Moments:** the rules in §8.4.
- **Tendencies:** "If a mistake fits one of the player's tendencies, say so briefly ('this is the third game where a loose knight cost you material'). Don't lecture about tendencies in every message."

## 8. Critical moments (Socratic step-through)

### 8.1 Choosing the moments

From the game's verified data:
1. All of the user's mistakes, blunders, and missed mates.
2. If that gives fewer than 3, add the user's largest inaccuracies until there are 3 (or none are left).
3. Cap at 6. If more qualify, keep the 6 biggest drops.
4. **Order chronologically.** The first mistake of the game is the first moment, even if a later one was bigger.

Store the moment list with the game summary.

### 8.2 The flow for one moment

1. **Set up.** The board jumps to the position before the user's mistake. The engine panel and Explain button are hidden.
2. **Intro** (`moment_intro`). The coach says what the user played, the eval before and after, and what happens next (the opponent's best reply line, from the engine's analysis of the position after the mistake). Then asks: *"What would you play instead, and why?"*
3. **Attempt.** The user plays a move on the board (it isn't added to the game tree as a variation yet) and can type their reasoning. The UI requires a move; the reasoning is optional but encouraged.
4. **Engine check.** The frontend runs the deep-dive tier (`SPEC.md` §5.3) on the position before (once per moment, cached) and on the position after the candidate. The backend grades the candidate (§8.3).
5. **Feedback** (`moment_feedback`).
   - **Solved** (grade `best` or `good`): praise, connect it to their reasoning, reveal the top engine move if it was different, explain the plan, and ask a follow-up question ("What do you think Black's best reply is?").
   - **Not solved:** acknowledge the reasoning, say what the engine shows goes wrong with their move, give one hint (§8.4), and invite another try.
   - **Same as the game move:** "That's what you played in the game. Let's look again." Counts as an attempt.
6. **Reveal** after the 2nd failed attempt (configurable), or when the user clicks "Show me." The coach explains the best move and plan, then the candidate's line is added to the tree as a variation so the user can explore it.
7. **Next moment** button moves on. After the last moment, the coach gives a short wrap-up (2–3 sentences, no new LLM task needed: use `moment_feedback` with a `wrap_up: true` flag).

The user can leave and return; moment progress is saved.

### 8.3 Grading a candidate

Using deep-dive results, from the user's point of view:
- `drop = wc(best) - wc(candidate)`, where `wc` is winning chances (`SPEC.md` §6.1), `best` is the root eval of the position before, and `candidate` is the eval of the position after the candidate move.
- Grades: `best` (the candidate is the engine's top move, or drop < 0.02), `good` (drop < inaccuracy threshold), then `inaccuracy` / `mistake` / `blunder` using the v1 thresholds.
- Solved = `best` or `good`.
- Also run the v1 detectors on the candidate move (treat it like a played move) to get theme facts about what's wrong with it. These power the hints.

### 8.4 Withholding and hints

Before the moment is revealed, the payload's `moment` object contains:

```json
{
  "index": 2,
  "of": 5,
  "state": "intro | attempt | solved | revealed",
  "game_move": { "san": "Nd4", "classification": "blunder", "eval_before": "+0.4", "eval_after": "-2.6", "themes": ["hung_piece"], "refutation_san": ["Qxd4", "..."] },
  "candidate": { "san": "Be3", "grade": "good", "eval_after": "+0.3", "themes": [], "refutation_san": [] },
  "attempt_number": 1,
  "max_attempts": 2,
  "hints_allowed": [
    { "level": 1, "kind": "candidate_problem", "text_facts": { "theme": "hung_piece", "piece": "bishop", "square": "c4" } },
    { "level": 2, "kind": "best_move_shape", "text_facts": { "piece_type": "bishop", "is_capture": false, "is_check": false } }
  ],
  "reveal": false,
  "best": null
}
```

- **While `reveal` is false, `best` is `null` and the top-line moves are not in `engine_lines`.** The coach cannot reveal what it was never given.
- `refutation_san` for the game move and the candidate is allowed (it shows what goes wrong with the user's own moves).
- `hints_allowed` is built by the backend: level 1 is about what's wrong with the user's candidate (from its theme facts); level 2 describes the best move's shape (piece type, whether it's a check or capture) without naming the move or square. The coach may only use the hints listed, one per message, lowest level first.
- When solved or revealed, `reveal` becomes true and `best` holds the top engine move and its lines.

**Leak check.** Extend v1 move validation: while `reveal` is false, the response must not contain the best move's SAN (or any first move of the top lines that would grade `good`). On a leak, regenerate once; if it leaks again, strip the move and log a `moment_leak` incident. Zero leaks is a v2 acceptance criterion.

## 9. Tendency tracking

### 9.1 Storing theme facts

Move v1's theme facts into a `game_theme_facts` table (one row per fact: user, game, theme, subtype, ply, severity, phase, user color). Backfill from existing v1 summaries.

### 9.2 Aggregation

- Order the user's analyzed games by date played (PGN `UTCDate`/`Date` header, falling back to upload time). The most recent game has age 0.
- Weight each game `w = 0.5 ** (age / 10)` (half-life of 10 games; configurable).
- Per theme, per game: per-move themes = number of occurrences; game-level themes (`slow_development`, `time_trouble`) = 1 if flagged, else 0.
- Weighted rate per theme = Σ(w × count) / Σ(w). Rank themes by weighted rate × severity weight (blunder 3, mistake 2, inaccuracy 1).
- Trend: compare the weighted rate over the last 5 games with the 5 before → `improving`, `worsening`, or `steady` (configurable margin).
- Also compute: weighted accuracy overall, by color, and by phase.
- Tendencies are **provisional** until the user has 5 analyzed games, and say so in the payload.

Recompute after every analyzed game and save a snapshot to `tendency_snapshots` (the v3 dashboard will chart these over time).

### 9.3 What the coach receives

`player.tendencies`: the top 5 themes, each as:

```json
{ "theme": "hung_piece", "label": "Leaving pieces undefended", "rate_per_game": 1.4, "trend": "worsening", "games_seen": 9, "provisional": false, "recent_example": { "game_id": 41, "move_number": 14, "move_san": "Nd4" } }
```

plus `accuracy_by_phase` and `accuracy_by_color`. Moves in `recent_example` count as allowed moves for validation.

## 10. Onboarding assessment

### 10.1 Requirements

12 games in the user's primary time control:
- As White: 3 wins and 3 losses.
- As Black: 3 wins and 3 losses.

Draws don't fill a slot.

### 10.2 Time-control category

From the PGN `TimeControl` header, estimated duration = base seconds + 40 × increment, then (Lichess's categories): < 180 s bullet, < 480 s blitz, < 1500 s rapid, otherwise classical. Ultrabullet counts as bullet. If the header is missing, the user picks the category for that game.

### 10.3 Flow

1. After first login, the user fills in their profile, then sees the onboarding page. They can skip it and analyze single games, but the baseline report needs all 12.
2. The page shows the 12-slot checklist (White wins 0/3, White losses 0/3, …).
3. The user pastes one or more games (multi-game paste is allowed here only). The backend splits and parses them and returns a table: players, result, date, time control. The user picks their color for each game; the UI then shows which slot each game fills, or why it can't be used (draw, wrong time control, slot full, non-standard start).
4. Accepted games are queued for analysis. The browser runs scan + verify for each game in turn with progress ("Game 3 of 12 — move 14 of 38"). Expect roughly 10 minutes. **Analysis must be resumable:** each game's status is stored on the server, so closing the tab and coming back continues where it stopped.
5. Per-game summaries and theme facts are built as each game finishes. **No per-game LLM synopsis during onboarding** (cost); the user can request one later from the game's page.
6. When all 12 are analyzed, the user generates the **baseline report**.

### 10.4 Baseline report

`task: "baseline_report"`, using `COACH_MODEL_SYNOPSIS`. The payload has the profile, the tendencies, accuracy by color and phase, and a compact summary of each game (result, color, opening name from headers, accuracy, counts, and key moments with their engine lines).

Format, about 400–600 words, markdown:
1. Overview of the player
2. Strengths (with an example game and move)
3. Top 3 things to work on, each with an example from their games
4. Openings: what they play as White and as Black, and whether it's working (results and opening-phase accuracy only; no invented theory)
5. A 2–4 week focus plan, with puzzle themes from the v1 allowed list
6. A question inviting them to open one of the example games and step through it

Stored and viewable any time from the profile. Every move named is validated against the data from all 12 games.

## 11. API (v2)

All endpoints except `/api/auth/redeem` and `/api/health` require a session.

| Method & path | Purpose |
|---|---|
| `POST /api/auth/redeem` | `{ token }` → sets session cookie |
| `POST /api/auth/logout` | Ends the session |
| `GET /api/me` / `PATCH /api/me` | Read / update profile |
| `GET /api/games` | My games: date, opponent, color, result, time control, accuracy, status |
| `POST /api/games` | v1 single-game upload (now user-scoped) |
| `GET /api/games/{id}` | Everything the analysis board needs: moves with evals and classifications, eval curve, stored engine results, moments, moment progress, synopsis, chat history |
| `POST /api/games/{id}/engine/scan`, `/engine/verify` | As v1 |
| `POST /api/games/{id}/synopsis` | As v1 |
| `POST /api/games/{id}/chat` | `{ message, path_uci, engine_result? }` → SSE, or `engine_request` as in v1 |
| `POST /api/games/{id}/chat/engine_result` | As v1 |
| `POST /api/games/{id}/explain` | `{ path_uci, engine_result? }` → SSE |
| `POST /api/games/{id}/moments/{idx}/start` | → SSE intro |
| `POST /api/games/{id}/moments/{idx}/attempt` | `{ candidate_uci, reasoning?, engine_results }` → SSE with a first `meta` event `{ grade, state }` |
| `POST /api/games/{id}/moments/{idx}/reveal` | → SSE reveal |
| `POST /api/onboarding/parse` | `{ pgn_text }` → parsed games table |
| `POST /api/onboarding/submit` | `{ games: [{ pgn, user_color, time_control_category? }] }` → slot assignments, created game ids |
| `GET /api/onboarding/status` | Slots, games, analysis status |
| `POST /api/onboarding/report` | → SSE baseline report |
| `GET /api/tendencies` | Current tendencies |
| `GET /api/health` | `{ ok: true }` |

## 12. Data model changes

- **New:** `users`, `sessions`, `invites`, `game_theme_facts`, `tendency_snapshots`, `moment_progress` (game, moment index, state, attempts JSON, revealed), `baseline_reports`.
- **`games`:** add `user_id`, `elo_at_analysis`, `time_control_category`, `user_result` (win/loss/draw), `played_at`, `status` (uploaded → scanned → verified → summarized), `source` (single/onboarding).
- **`engine_results`:** add `user_id`; allow variation positions (keyed by game + normalized FEN + tier).
- **`chat_messages`:** add `path_uci`.
- **`llm_usage`:** add `user_id` and `task`.

Optional safety valve, off by default: `USER_DAILY_TOKEN_LIMIT` in config. v4 replaces it with credits.

## 13. v2 milestones and checkpoints

Stop for owner review at every ✅.

- **M0 — Reconcile and plan.** Write `docs/v1-as-built.md` (§3) and an implementation plan for M1–M7 with data models and interfaces. List spec changes you recommend. ✅ *Checkpoint.*
- **M1 — Accounts.** Alembic baseline + v2 migrations, users/invites/sessions, CLI commands, profile page, user scoping on every endpoint (with isolation tests), v1 data assigned to the owner, access code removed. ✅ *Checkpoint: auth and isolation tests, plus a walkthrough of the login flow.*
- **M2 — Analysis board.** My games list, game page loaded from the database, chessground board, game tree with variations, move list with glyphs, eval graph, live engine panel, arrow keys. ✅ *Checkpoint: demo on a fixture game.*
- **M3 — Position-aware chat and Explain.** Path resolution, payload v2, engine results for the current position, updated tool, Explain endpoint and button, prompt caching for the game summary. ✅ *Checkpoint: transcripts from a mainline position and a variation.*
- **M4 — Critical moments.** Selection, state machine, grading, candidate detectors, hint builder, withholding, leak check, moment UI, saved progress. ✅ *Checkpoint: full walkthrough of 2 fixture games, including the exact payloads sent before reveal.*
- **M5 — Tendencies.** Theme-facts table and backfill, aggregation, snapshots, tendencies in the payload. ✅ *Checkpoint: tendency output for the owner's games, with the math shown.*
- **M6 — Onboarding and baseline report.** Parse/submit, slot validation, time-control categories, resumable queue, baseline report. ✅ *Checkpoint: the owner's real 12-game baseline report.*
- **M7 — Harden and ship.** Playwright end-to-end tests for login → upload → board → moment → chat (engine faked), error and loading states, README, deploy update. ✅ *Checkpoint: final review.*

**v2 is done when:**
- The owner completes onboarding with 12 of their own games and agrees with the baseline report.
- The owner steps through critical moments on 5 games, and the coach never reveals the best move before the user has tried (zero `moment_leak` incidents, plus tests).
- Chat answers correctly reflect the board position, including in variations.
- One user can never see another user's data.
- All tests, lint, and type checks pass.

---

## 14. Roadmap (do not build in v2)

### v3 — Polish and richer coaching
- Coach returns structured annotations (`{"arrows": [["e4","d5","green"]], "highlights": ["f7"]}`), validated against engine lines, drawn on the board.
- Guided line stepping: walk through a recommended line move by move with an explanation at each step.
- Dashboard: top focus areas, mistake types over time (from `tendency_snapshots`), accuracy trend, recent games.
- Puzzle-theme recommendations linked to the matching Lichess puzzle themes.
- Saved variations, full keyboard shortcuts, UI polish, loading states.
- Optional: import games from Lichess / Chess.com by username.

### v4 — Production
- Google sign-in replacing invite links.
- Stripe subscriptions (e.g. $10/month including a monthly API credit allowance) and one-time credit top-ups.
- Credit metering from `llm_usage`, usage tracker in the UI, block or warn at zero.
- Cost controls: prompt caching, model routing, compact payloads.
- AWS deployment (App Runner or ECS, RDS Postgres, Secrets Manager), monitoring, backups, rate limiting.
- Terms of service, privacy policy, account deletion.
- Later: Chessly-style opening courses and drills.