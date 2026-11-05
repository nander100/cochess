# Claude Code kickoff prompt — CoChess v3

## Setup before pasting

1. **Finish v2.** Make sure everything on the `v2` branch is committed (`git status` shows nothing to commit), merge it into your main branch, and tag it: `git tag v2`.
2. **Start a branch:** `git checkout -b v3`.
3. **Add the files:**
   - Put `SPEC_V3.md` in the project root. Keep `SPEC.md` and `SPEC_V2.md` where they are.
   - Replace `CLAUDE.md` with the new one. Claude Code recovers anything the v2 version had learned from git (see the prompt).
4. **Decide about game import** (Lichess / Chess.com by username). It's optional milestone M7, and Claude Code will ask you at M0. If you want it, have your usernames ready.
5. Start Claude Code in the project folder (`claude`), press **Shift+Tab** for plan mode, and paste the prompt below.

---

## Prompt to paste

We're starting v3 of CoChess. v2 is finished and tagged `v2`.

Read `CLAUDE.md` and `SPEC_V3.md` in full first. `SPEC_V2.md` and `SPEC.md` are the earlier specs; use them where `SPEC_V3.md` points to them. `docs/v1-as-built.md` describes what v1 actually became.

`CLAUDE.md` was just replaced with a v3 version. Run `git diff v2 -- CLAUDE.md` and carry over anything the v2 version had learned that's still true (commands, conventions, gotchas) into the new file. Show me what you carried over.

Build **v3 only** (SPEC_V3 §1–§12). v4 in §13 is context only.

The four rules that matter most:
1. **The engine analyzes, the LLM explains.** The coach never calculates or invents moves, and the backend validates every move it mentions.
2. **Withhold, don't instruct.** The best move of an unsolved critical moment stays out of every payload, arrow, and walkthrough.
3. **Never trust the client.** The backend replays UCI paths with python-chess, checks browser engine results against the replayed position, and scopes every query by user.
4. **Every visual claim is checked.** Coach arrows and highlights are validated before they're drawn, and green arrows only ever mark good moves.

Two things from user feedback that shape this version:
- **No default color.** Testers had games analyzed from the wrong side because White was pre-selected. The user must pick their color before entering a game. Do this first in M1 and commit it on its own.
- **The coach should talk like a person, not an engine.** Everyday language, no strings of moves in the text, and line links that play out on the board instead (SPEC_V3 §9, milestone M5).

How I want to work:
- Start with **M0**: compare the codebase to `SPEC_V2.md` and write `docs/v2-as-built.md` (SPEC_V3 §3). Then write an implementation plan for M1–M8 with data models, migrations, and interfaces. Reuse v2 code wherever it fits (game tree, path replay, payload builder, move validation and leak check, tendency snapshots, fake engine transport). List anything in `SPEC_V3.md` that's ambiguous, conflicts with the v2 code, or that you'd change, with your recommendation. Ask me whether to build M7 (game import). Then stop and wait for my approval.
- Work through the milestones in order. Stop at every ✅ checkpoint, show me evidence (test output, Playwright screenshots for UI work, and real output on my games for coach features), and wait for my go-ahead.
- Commit after each working step with a clear message, on the `v3` branch.
- Write tests alongside code. Keep `uv run pytest`, `ruff`, `mypy`, `npm test`, `npm run lint`, and `npx playwright test` passing.
- Stop and ask before adding a dependency not listed in `CLAUDE.md`, changing an approved schema, removing earlier behavior the spec doesn't mention, or making a decision the spec doesn't cover.
- If you learn a command or convention while working, update `CLAUDE.md`.

Verify rather than assume: chessground's drawable/auto-shapes API, Lichess's puzzle-theme names and training URLs, the Lichess and Chess.com public game APIs (endpoints, rate limits, and Chess.com's User-Agent requirement), Anthropic's current syntax for forcing a specific tool, the Recharts API, and the license of any piece set or board theme you add.

Begin with M0.
