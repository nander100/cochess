# Claude Code kickoff prompt — CoChess v2

## Setup before pasting

1. **Commit v1.** In your project folder, make sure everything is committed (`git status` shows nothing to commit). Tag it so you can always get back: `git tag v1`.
2. **Start a branch:** `git checkout -b v2`.
3. **Add the files:**
   - Put `SPEC_V2.md` in the project root. Keep the old `SPEC.md` where it is.
   - Replace `CLAUDE.md` with the new one. Don't worry about losing anything Claude Code added to it during v1; the prompt below has it recover that from git.
4. **Have 12 of your own games ready** for the onboarding milestone (M6): in your main time control, 3 wins and 3 losses as White, 3 wins and 3 losses as Black.
5. Start Claude Code in the project folder (`claude`), press **Shift+Tab** for plan mode, and paste the prompt below.

---

## Prompt to paste

We're starting v2 of CoChess. v1 is finished and tagged `v1`.

Read `CLAUDE.md` and `SPEC_V2.md` in full first. `SPEC.md` is the original v1 spec; use it for reference where `SPEC_V2.md` points to it.

`CLAUDE.md` was just replaced with a v2 version. Run `git diff v1 -- CLAUDE.md` and carry over anything the v1 version had learned that's still true (commands, conventions, gotchas) into the new file. Show me what you carried over.

Build **v2 only** (SPEC_V2 §1–§13). v3 and v4 in §14 are context only.

The three rules that matter most:
1. **The engine analyzes, the LLM explains.** The coach never calculates or invents moves, and the backend validates every move it mentions.
2. **Withhold, don't instruct.** During critical-moment exercises, the best move is left out of the payload until the user solves the moment or it's revealed. The leak check is only a backstop.
3. **Never trust the client.** The frontend sends UCI move paths; the backend replays them with python-chess. Browser engine results are checked against the replayed position and never shared across users. Every query is scoped by user.

How I want to work:
- Start with **M0**: compare the codebase to `SPEC.md` and write `docs/v1-as-built.md` (SPEC_V2 §3). Then write an implementation plan for M1–M7 with the data models, migrations, and interfaces between modules. Reuse v1 code wherever it fits (engine worker, fake engine transport, detectors, payload builder, move validation, the `analyze_position` round trip). List anything in `SPEC_V2.md` that's ambiguous, conflicts with the v1 code, or that you'd change, with your recommendation. Then stop and wait for my approval.
- Work through the milestones in order. Stop at every ✅ checkpoint, show me evidence (test output, and real output on my games where the milestone asks for it, including exact payloads at M4), and wait for my go-ahead.
- Commit after each working step with a clear message, on the `v2` branch.
- Write tests alongside code. Keep `uv run pytest`, `ruff`, `mypy`, `npm test`, `npm run lint`, and (from M7) `npx playwright test` passing.
- Stop and ask before adding a dependency not listed in `CLAUDE.md`, changing an approved schema, removing v1 behavior the spec doesn't mention, or making a decision the spec doesn't cover.
- If you learn a command or convention while working, update `CLAUDE.md`.

Verify rather than assume: the current chessground and chess.js APIs, Lichess's time-control category thresholds, Alembic's SQLite limitations (use batch mode for altering tables), and Anthropic's current prompt-caching syntax for caching more than one block.

Begin with M0.