# CoChess — v3 Spec

Status: **v3 in scope.** This builds on v2 (`SPEC_V2.md`) and v1 (`SPEC.md`), both kept for reference. Where they disagree, this file wins. Sections 1–12 define v3 (§12 is the milestone plan). Section 13 is the roadmap for v4.

---

## 1. What v3 adds

v2 made CoChess an analysis board with a coach that teaches move by move. v3 makes it pleasant to use every day and makes the coaching visual:

1. **UI foundation and polish.** A consistent design system, light and dark themes, proper loading/empty/error states, a settings page, and full keyboard shortcuts.
2. **Saved variations and PGN export.** Lines the user explores are kept, and games export with variations and coach notes.
3. **Coach annotations.** The coach can draw arrows and highlight squares on the board. Every arrow is checked against the engine data before it's drawn.
4. **Guided line walkthroughs.** Step through an engine line move by move, with a short explanation and arrows at each step.
5. **Dashboard.** The user's home page: focus areas, mistake types over time, accuracy trend, recent games, and unfinished moments.
6. **Puzzle links.** When the coach recommends a puzzle theme, it becomes a link to that theme in Lichess's puzzle trainer.
7. **Plain-language coaching and line playback.** The coach talks about the game in everyday words instead of quoting engine lines. When a line matters, the coach inserts a link that plays it out on the board, one move every 1.5 seconds, stopping once the difference in the position is clear.
8. **Color selection fix (user feedback).** No color is selected by default; the user must pick White or Black before entering a game.
9. **Game import from Lichess and Chess.com (optional).** The owner decides at M0 whether this milestone is built.

**Rules carried forward:**
- **The engine analyzes, the LLM explains.**
- **Withhold, don't instruct.** Secrets stay out of the payload.
- **Never trust the client.** Paths are replayed on the backend; engine results are checked and never shared across users.

**New rule for v3: every visual claim is checked.** An arrow is a claim about a move. The backend validates every arrow and highlight against python-chess and the engine data. Anything that fails is dropped, never drawn.

## 2. v3 scope

**In:** everything in §1.

**Out (v4+):** Google sign-in, payments and credits, production AWS deployment, mobile layout, Chessly-style opening courses and in-app puzzles, coach-written weekly summaries.

## 3. Step zero: reconcile with v2 as built

As in v2, before planning:
1. Compare the codebase to `SPEC_V2.md` and write `docs/v2-as-built.md`: actual endpoints, schemas, payload shapes, moment flow, tendency math, and anything that differs from the spec.
2. Adjust this plan to fit the real code and list the adjustments at the M0 checkpoint.
3. Ask the owner whether to build the optional import milestone (M7).

Reuse v2 pieces wherever they fit: the game tree, path replay, payload builder, move validation and leak check, tendency snapshots, and the fake engine transport.

## 4. UI foundation and polish

Done first so every later feature is built on it.

### 4.1 Design system

- **Design tokens** as CSS custom properties: colors, spacing scale, type scale, radii, shadows. Defined once; no hard-coded colors or sizes in components.
- **Themes:** light, dark, and "match system". Dark is the default, like most chess sites. Both must meet WCAG AA contrast for text.
- **Shared components:** button, icon button, tabs, card, tooltip, modal, toast, skeleton loader, empty state, error state. Every page uses these.
- **Semantic colors for chess meaning,** used everywhere (move list glyphs, eval graph dots, arrows, dashboard): best/good (green), inaccuracy (yellow), mistake (orange), blunder (red), plan/idea (blue). Never rely on color alone; glyphs and labels always accompany it.
- **Desktop widths 1280–1920 px.** The layout must not break between those widths. Mobile is still out.

### 4.2 States

Every screen that loads data has a skeleton loader, an empty state that tells the user what to do next, and an error state with a retry. Streaming coach replies show a typing indicator, and engine work shows progress. Errors from the backend appear as toasts with a plain-language message.

### 4.3 Settings page

Theme, coach detail level (§9.3), line playback speed (§9.5), board color scheme (3 options), piece set (the default plus one alternative; check each set's license before adding), "show engine panel by default", "sounds on move" (on/off), and the keyboard shortcut list. Stored per user in `user_settings`.

### 4.4 Keyboard shortcuts

| Key | Action |
|---|---|
| ← / → | Previous / next move |
| ↑ / Home | Start of game |
| ↓ / End | End of game (or end of current variation) |
| F | Flip board |
| E | Toggle engine panel (disabled during an unsolved moment) |
| X | Explain (disabled during an unsolved moment) |
| N | Next critical moment |
| W | Walk through the top engine line (§7) |
| Space | Pause / resume line playback (§9.5) |
| Esc | Leave walkthrough or playback / close modal |
| / | Focus the chat input |
| ? | Show shortcut help |

Shortcuts are ignored while typing in an input.

### 4.5 Accessibility basics

Visible focus states, labels on icon buttons, the move list readable by screen readers (SAN with move numbers), and reduced motion respected for board animations.

### 4.6 Color selection (user feedback — do this first in M1)

Testers reported that White was pre-selected, so games were analyzed from the wrong side. Fix everywhere a color is chosen:

- **Single-game upload form:** the color control ("I played White" / "I played Black") comes **before** the PGN box and starts with **nothing selected**. The PGN box and the Analyze button stay disabled until a color is chosen, with helper text: "Choose the color you played first."
- **Onboarding multi-game table** (SPEC_V2 §10.3): every row's color starts unselected. Submit is disabled until every row has a color, and rows without one are highlighted.
- **Import review table** (§10, if built): rows also start unselected. If the linked username matches a player, show a "Detected: you played Black" hint and a "Use detected colors" button, but don't pre-select.
- **Backend:** `user_color` is required with no default in every request schema. A missing or invalid color returns 422 with a clear message. Search the codebase for any `"white"` default (schemas, forms, fixtures, state initializers) and remove it.
- **Tests:** API rejects a missing color; the form can't be submitted without a color; a Playwright test confirms neither option is selected when the page loads.

## 5. Saved variations and PGN export

### 5.1 Saving

- Variations the user plays on the board are saved automatically (debounced) per game, per user.
- Store each variation as its starting path plus its moves (UCI). The backend replays and validates every saved path.
- In the move list: right-click (or a menu button) on a variation offers "Delete variation" and "Promote to main line of my notes" (reorders display only; never changes the actual game).
- Candidate moves from critical moments that were added to the tree in v2 are saved the same way.

### 5.2 PGN export

"Export PGN" downloads the game with:
- The user's saved variations.
- NAGs on the user's moves (`?!`, `?`, `??`).
- Evals as `[%eval]` comments on the mainline.
- A short comment at each critical moment with the classification and the best move (always included: the export is for after the user has finished with the game).
- Headers from the original PGN preserved.

Generated by the backend with python-chess. Round-trip test: the exported PGN re-imports and replays correctly.

## 6. Coach annotations

### 6.1 How the coach marks up the board

The coach writes inline tags in its reply:

```
After {{move:Qxd4}} your knight is gone <board arrows="d1d4:red" squares="d4:red"/>, so look for a move that defends d4 first.
```

- `arrows`: comma-separated `fromto:color` (UCI squares).
- `squares`: comma-separated `square:color`.
- Colors: `green` (good move), `red` (mistake or threat), `yellow` (inaccuracy or caution), `blue` (plan or idea).
- At most 4 arrows and 4 squares per tag, and at most 3 tags per message.
- **Chat annotations always refer to the position on the board when the message was sent.** Anything about later positions goes through a walkthrough (§7), where every step has its own position.

The backend strips the tags from the text, validates them (§6.2), and sends the valid ones to the frontend as separate SSE `annotation` events tied to their place in the text. Invalid tags are dropped and logged.

### 6.2 Validation rules (position P)

An **arrow** is drawn only if one of these holds:
- **Move arrow:** `from→to` is a legal move in P (for the side to move) that appears in the data the coach was given: the game move from P, the first move of an engine line from P, the user's candidate, or the next move of the user's variation.
  - `green` only if that move grades `best` or `good` (SPEC_V2 §8.3) against the engine lines for P.
  - `red` only if it grades `mistake` or worse, or it's the game's mistake.
  - `yellow` only if it grades `inaccuracy`.
  - `blue` for any move that appears in the data.
- **Threat arrow:** the piece on `from` attacks `to` in P (python-chess `attacks`), for either side. Allowed colors: `red` and `yellow`. Never `green`.
- **Plan arrow:** `blue` only, and some move in the engine lines from P goes from `from` to `to` (e.g. a knight route the engine actually plays).

A **square highlight** is allowed on any square, in `red`, `yellow`, `green`, or `blue`.

**Leak check (extends SPEC_V2 §8.4):** while a moment is unrevealed, any arrow or highlight that points out the best move (its from-square, to-square, or the move itself) is dropped and logged as `moment_leak`, and the reply is regenerated once.

### 6.3 Drawing

- Use chessground's drawable auto-shapes for arrows and highlights.
- When a coach message arrives, its annotations are drawn. Each tag shows as a small board icon at its place in the text; hovering or clicking it draws only that tag's shapes.
- Shapes clear when the user moves to a different position, and come back if they return to it.
- The user's own drawn arrows (right-click drag, as in Lichess) still work and don't mix with the coach's.

### 6.4 Prompt changes

Add an "Annotations" section to the base prompt: the tag format, the colors and what each means, "use them when an arrow makes the explanation clearer, usually one tag per message", and "only draw moves and threats that are in the data".

## 7. Guided line walkthroughs

### 7.1 What can be walked through

A line of up to 10 plies from a position:
- An engine line from the engine panel or the stored analysis (W shortcut walks the top line).
- The refutation of a mistake (what happens after the user's bad move).
- The best line of a critical moment, **only after it's solved or revealed**.
- A variation the user played.

Each entry point shows a "Walk me through it" button.

### 7.2 Building the walkthrough

1. The frontend sends the starting path and the line (UCI) to the backend, which replays and validates it.
2. **Per-step evals:** the frontend runs the scan tier (SPEC.md §5.3) on each position along the line, with progress, and sends the results. Results are checked against the replayed positions.
3. **Move facts (deterministic, python-chess):** for each step: the move in SAN, the side, the piece moved, whether it captures (and what), whether it checks, enemy pieces newly attacked and undefended, the mover's pieces newly left hanging, material balance, the eval after, and the eval change. Reuse the v1 detectors where they fit.
4. **One coach call for the whole line** (not one per step), using `COACH_MODEL_CHAT`, with a forced tool so the output is structured:

```json
{
  "name": "line_walkthrough",
  "input_schema": {
    "type": "object",
    "properties": {
      "intro": { "type": "string" },
      "steps": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "index": { "type": "integer" },
            "text": { "type": "string", "description": "≤ 50 words" },
            "arrows": { "type": "array", "items": { "type": "string", "description": "fromto:color" } },
            "squares": { "type": "array", "items": { "type": "string", "description": "square:color" } }
          },
          "required": ["index", "text"]
        }
      },
      "summary": { "type": "string" }
    },
    "required": ["intro", "steps", "summary"]
  }
}
```

5. Validate: one step per ply, every move named in the text is in the line or the move facts, and each step's annotations pass §6.2 against that step's position.
6. Cache the result per user, keyed by starting position and line, so walking the same line again costs nothing.

The payload is the v2 payload plus `walkthrough: { start_path_san, line_san, steps: [move facts...] }`. Prompt: "Follow the plain-language rules (§9.2) and use move tags (§9.4). Explain each move's purpose in one or two sentences: what it threatens, what it defends, or why it's better than the obvious alternative. Point out the moment the advantage becomes clear. Match the player's level."

### 7.3 Walkthrough UI

- A stepper panel replaces the moment/moves tab while active: intro, then ◀ / ▶ (and ← / →) through the steps, with the board showing each step's position, its arrows, and its text.
- Eval bar follows the step's eval.
- "Back to game" (or Esc) returns to where the user was.
- "Save as variation" adds the line to the user's saved variations.
- Walkthroughs don't change the game tree unless saved.

## 8. Dashboard and puzzle links

### 8.1 Dashboard (the home page after login)

In this order:
1. **Focus areas:** the top 3 non-provisional tendencies, each with a plain-language label, trend (improving / worsening / steady), rate per game, a "See an example" link that opens the game at that moment, and puzzle-theme links (§8.2).
2. **Continue where you left off:** games with unfinished critical moments.
3. **Mistake types over time:** a line chart of the weighted rate per theme from `tendency_snapshots`, top 5 themes, with a toggleable legend.
4. **Accuracy trend:** one dot per game (marked by result: win/loss/draw), a rolling average of the last 10 games, toggles for color, and small bars for opening/middlegame/endgame accuracy.
5. **Recent games:** the last 10 with opponent, result, accuracy, and critical moments solved (e.g. 3/5).
6. **Onboarding card** if the 12-game assessment isn't finished; otherwise a link to the baseline report.

Filters at the top: time control category, color, and range (last 10 / 25 / all games).

- One endpoint, `GET /api/dashboard`, returns all of this computed on the backend. It must respond in under 300 ms for a user with 200 games (add indexes as needed and test it).
- Empty states guide new users: "Analyze a game or start your 12-game assessment to see your trends."
- No LLM calls on the dashboard.

### 8.2 Puzzle-theme links

- The coach writes recommended themes as tags, e.g. `{{puzzle:fork}}`. The backend accepts only themes in the allowed list (SPEC.md §7.3) and drops anything else.
- The frontend renders each as a chip linking to that theme in Lichess's puzzle trainer.
- A mapping table in config links CoChess themes to Lichess puzzle themes, used for the dashboard's focus-area chips. Example (verify every slug and URL against Lichess before finalizing):

| CoChess theme | Lichess puzzle themes |
|---|---|
| `hung_piece` | hangingPiece |
| `missed_tactic` (fork / pin / skewer / discovered_attack / back_rank) | fork / pin / skewer / discoveredAttack / backRankMate |
| `missed_capture_or_check` | hangingPiece, mateIn1 |
| `king_safety` | kingsideAttack, defensiveMove |
| `endgame_technique` | endgame, rookEndgame, pawnEndgame |
| `slow_development`, `pawn_structure`, `time_trouble` | none (coach advice only) |

## 9. Plain-language coaching and line playback

### 9.1 The problem

The coach quotes engine lines directly ("after 14...Qxd4 15.Nxd4 Bxd4 16.c3 Bb6 the eval is -2.6"). Experienced players can follow that; newer players can't. The coach should talk about the game the way a human coach would at the board, and *show* lines instead of reciting them.

### 9.2 Plain-language rules (prompt changes)

Add a "How to talk about moves" section to the base prompt, and apply it to every task (synopsis, chat, explain, moments, walkthroughs, baseline report):

- **Describe ideas, not sequences.** Say what a move does and why: "your knight left d4 without protection, and Black's queen simply took it." Not a string of moves.
- **Never write more than one move in a row in the text.** If a sequence matters, use a line link (§9.4).
- **Name pieces and squares in words:** "the knight on f3", "the pawn on e5", "castle on the kingside".
- **Evals in words first.** "Black is winning" or "the position is about equal", with the number in parentheses only when the detail level allows it (§9.3).
- **Avoid jargon at lower levels** (e.g. "zwischenzug", "prophylaxis"); if a term is useful, explain it in a few words the first time.
- Keep everything else from earlier versions: grounded in the data, encouraging, Socratic.

### 9.3 Coach detail level

A new setting, "Coach detail level", with three values. The default comes from the rating band, and the user can change it in Settings.

| Level | Default for | Moves shown as | Evals shown as |
|---|---|---|---|
| Plain | beginner (< 1000) | Words only: "knight takes on e5" | Words only |
| Standard | intermediate (1000–1800) | Words, with notation on hover | Words, number in parentheses |
| Technical | advanced (> 1800) | Notation: "Nxe5" | Number, words optional |

Add `detail_level` to `player` in the payload so the coach writes at the right level.

### 9.4 Move tags and line links

To keep move validation working while the text reads naturally, the coach no longer writes notation directly. It uses two tags:

- **Move tag:** `{{move:Nxe5}}`. The backend validates the SAN against the data (as in v1), then sends it to the frontend as a structured token `{ san, words }`. `words` is generated by the backend with python-chess ("knight takes on e5", "castles kingside", "pawn to e8, promoting to a queen", "...with check"). The frontend shows words, notation, or both according to the detail level.
- **Line link:** `{{line:here.engine1|see what happens if you take}}`, written as `{{line:<position>.<line>|<link text>}}`.
  - `<position>`: `here` (the position the message is about) or `km<N>` (key moment N from the game summary).
  - `<line>`: `engine1`–`engine4` (engine lines from that position), `refutation` (the user's move at that position followed by the opponent's best reply line), `candidate` (the user's moment candidate followed by its refutation), `best` (only after a moment is solved or revealed), or `variation` (the user's current variation).
  - The backend resolves the reference to real UCI moves from the payload data. The coach never writes the moves of a line itself. Unknown references, or `best` before reveal, are dropped and logged (`best` before reveal also counts as a `moment_leak`).
  - At most 3 line links per message.

**Bare notation outside a tag is a validation failure:** regenerate once; if it happens again, convert any valid SAN into a move tag and drop anything invalid.

The same rules apply to walkthrough step text (§7.2): steps use move tags rather than raw notation.

### 9.5 Line playback

Clicking a line link plays the line on the board:

1. If the link is for a different position (`km<N>`), the board jumps there first.
2. The board enters **playback mode**: a small control bar appears under the board (pause/play, step back/forward, replay, "Back to position").
3. Moves play automatically, **one every 1.5 seconds** (configurable in Settings from 0.75 to 3 seconds), with the normal move animation and last-move highlight.
4. Playback **stops at the settle point** (§9.6), where the difference in the position is clear. A short caption appears, built from deterministic move facts (§7.2), not the LLM: e.g. "Black has won a knight" or "White's king is now in a mating net".
5. Buttons at the stop: "Continue the line" (plays any remaining moves at the same speed), "Walk me through it" (opens the §7 walkthrough for this line), "Save as variation", and "Back to position".
6. Any user input on the board, ←/→, or Esc pauses playback. Esc or "Back to position" returns to where the user was.
7. Playback never changes the game tree unless the user saves it.
8. Reduced-motion users get instant moves with the same timing.

### 9.6 Settle point (when to stop)

The stop point is decided by a deterministic rule on the backend, never by the LLM:

1. When the coach message arrives, the frontend runs the scan tier (SPEC.md §5.3) on each position of each linked line in the background (at most 10 plies each) and posts the results. If the user clicks before this finishes, playback starts anyway and the settle point is applied once it's known.
2. The backend computes, for each ply *k* of the line: win% from the starting player's point of view, material balance, and whether the move is a check or capture.
3. The settle point is the first *k* (at least 2 plies, so the reply is always shown; for `refutation` and `candidate`, at least 2 plies after the user's move) where:
   - win% has moved at least 10 points from the start of the line, **or** material has changed by 2 or more points, **and**
   - the position is quiet: ply *k* isn't a check, and the next move in the line isn't a capture (so playback never stops in the middle of an exchange).
4. If no ply qualifies, play the whole line. Stop immediately at checkmate.
5. All thresholds are in config. Unit-test the rule on hand-built lines (a simple piece win, an exchange that ends even, a mate, a quiet line).

The caption at the settle point comes from comparing move facts between the start and the stop: material won or lost, a newly passed pawn, the king left exposed, or the eval change in words.

## 10. Game import (optional milestone)

Built only if the owner approves at M0.

- **Linked accounts:** on the profile, the user can add their Lichess and/or Chess.com username. Usernames are public; no passwords or OAuth.
- **Import:** "Import recent games" fetches the user's latest games (default 20, max 50) from the platform's public API, on the backend. Filters: time control category and date range.
- **Review table:** imported games appear in the same table as multi-game paste (SPEC_V2 §10.3). Colors start unselected; a matching linked username only produces a "detected" hint (§4.6). Already-imported games are marked and skipped (dedupe by platform + game id).
- Imported games go through the normal pipeline: single-game analysis, or filling onboarding slots.
- Elo stays manual (the owner's decision in earlier planning). The platform rating can be shown next to the Elo field as a hint only.
- Respect each platform's rate limits and API terms. Chess.com asks API clients to identify themselves in the `User-Agent`; use a configurable app name and contact from env vars, never hard-coded.
- Handle errors clearly: user not found, private or empty account, rate limited, platform down.

## 11. API and data model changes

### 11.1 New and changed endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/settings` / `PATCH /api/settings` | User settings |
| `GET /api/games/{id}/variations` / `PUT /api/games/{id}/variations` | Load / save the user's variations (validated) |
| `GET /api/games/{id}/export.pgn` | PGN export (§5.2) |
| `POST /api/games/{id}/walkthrough` | `{ start_path_uci, line_uci, step_results }` → walkthrough JSON (cached) |
| `GET /api/dashboard?tc=&color=&range=` | Dashboard data |
| `POST /api/lines/{line_id}/playback` | `{ step_results }` → `{ moves, settle_ply, caption, evals }` (§9.6) |
| `PATCH /api/me/linked-accounts` | Lichess / Chess.com usernames (import milestone only) |
| `POST /api/import` | `{ platform, max, tc?, since? }` → review table (import milestone only) |

Chat, explain, moment, synopsis, and baseline-report SSE streams gain three events:
- `annotation`: `{ tag_index, char_offset, arrows: [...], squares: [...] }`
- `move`: `{ char_offset, san, words }`
- `line_link`: `{ char_offset, line_id, label, start_path_uci, moves_uci }`

All request schemas that take `user_color` require it, with no default (§4.6).

### 11.2 Data model

- **New:** `user_settings`, `game_variations` (game, user, start path, moves, created/updated), `walkthroughs` (user, game, start path, line, steps JSON, created_at), `annotation_log` (dropped or leaked annotations with reason), and for import: `linked_accounts`, plus `external_source` and `external_id` on `games` (unique per user).
- **`line_links`:** id, user, game, message, source reference (e.g. `km2.refutation`), start path, moves, step evals, settle ply, caption.
- **`user_settings`:** add `coach_detail_level` (default from rating band) and `playback_seconds` (default 1.5).
- **`chat_messages`:** store validated annotations, move tokens, and line links with each coach message so they redraw when the chat is reloaded.
- **`llm_usage`:** add the `walkthrough` task.
- Indexes needed for the dashboard query target.

## 12. v3 milestones and checkpoints

Stop for owner review at every ✅.

- **M0 — Reconcile and plan.** Write `docs/v2-as-built.md` (§3) and an implementation plan for M1–M8. List recommended spec changes. Ask whether to build M7 (import). ✅ *Checkpoint.*
- **M1 — Color fix and UI foundation.** First, the color-selection fix (§4.6), committed on its own so it can ship right away. Then design tokens, themes, shared components, loading/empty/error states across existing pages, settings page, keyboard shortcuts and help overlay, accessibility basics. ✅ *Checkpoint: the color-fix tests, plus Playwright screenshots of every page in light and dark at 1280 and 1920 px.*
- **M2 — Saved variations and PGN export.** Auto-save, delete/promote, export with round-trip test. ✅ *Checkpoint: an exported PGN from a fixture game opened in a Lichess-style viewer.*
- **M3 — Coach annotations.** Tag parsing, validation, `annotation` SSE events, drawing and per-tag hover, stored with chat history, leak-check extension, prompt update. ✅ *Checkpoint: transcripts with screenshots, plus the log of dropped annotations from a test run.*
- **M4 — Line walkthroughs.** Move-facts builder, per-step scan, forced-tool coach call, validation, caching, stepper UI, all entry points. ✅ *Checkpoint: walkthroughs of 3 lines from the owner's games.*
- **M5 — Plain-language coaching and line playback.** Prompt rewrite (§9.2) across all tasks, detail-level setting, move tags with backend-generated words, line links and reference resolution, bare-notation check, background scan of linked lines, settle-point rule and captions, playback mode and controls, stored with chat history. ✅ *Checkpoint: the same 3 coach replies from the owner's games at each detail level (before and after this milestone), plus screen recordings or screenshot sequences of 3 line playbacks showing where each one stopped and why.*
- **M6 — Dashboard and puzzle links.** Endpoint with the performance target, charts, filters, focus areas with example links, puzzle chips, mapping table. ✅ *Checkpoint: the owner's real dashboard.*
- **M7 — Game import (optional).** Linked accounts, both platforms, review table, dedupe, error handling. ✅ *Checkpoint: importing the owner's recent games from each platform.*
- **M8 — Harden and ship.** Playwright end-to-end tests for color selection, annotations, walkthroughs, line playback, dashboard, export, and import (with platform APIs faked); performance check; README; deploy update. ✅ *Checkpoint: final review.*

**v3 is done when:**
- No color is ever pre-selected, and no game can be submitted without one.
- Coach replies contain no raw notation outside move tags, and no more than one move in a row in the text. A newer player (under 1000) the owner trusts can follow a Plain-level synopsis of one of their own games.
- Line playback stops at a point the owner agrees shows the difference, on 5 lines from their games, and never stops in the middle of an exchange.
- No arrow is ever drawn that fails validation (tests plus the `annotation_log`), and green arrows only ever mark good moves.
- The owner agrees with the walkthroughs on 5 lines from their own games.
- The dashboard's focus areas match what the owner recognizes from their baseline report and recent games, and it loads within the target.
- Still zero `moment_leak` incidents, including through annotations.
- Exported PGNs re-import cleanly.
- All tests, lint, type checks, and end-to-end tests pass.

---

## 13. Roadmap (do not build in v3)

### v4 — Production
- Google sign-in replacing invite links.
- Stripe subscriptions (e.g. $10/month including a monthly API credit allowance) and one-time credit top-ups.
- Credit metering from `llm_usage`, a usage tracker in the UI, and block or warn at zero.
- Cost controls: prompt caching, model routing, compact payloads, walkthrough caching.
- AWS deployment (App Runner or ECS, RDS Postgres, Secrets Manager), monitoring, backups, rate limiting.
- Terms of service, privacy policy, account deletion and data export.

### Later
- Chessly-style opening courses and drills.
- In-app puzzles drawn from the user's own mistakes.
- Mobile layout.
