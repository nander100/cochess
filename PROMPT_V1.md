# Claude Code kickoff prompt — CoChess v1

Setup before pasting:
1. Create an empty folder `cochess/` and `git init` it.
2. Put `CLAUDE.md` and `SPEC.md` in the root.
3. Have an Anthropic API key ready (it goes in `backend/.env`, never in the repo).
4. Pick 5 of your own games as PGN files; you'll add them at milestone M1.
5. Start Claude Code in the folder, switch to plan mode (Shift+Tab), and paste the prompt below.

---

## Prompt to paste

We're building CoChess, an AI chess coach for intermediate players. Read `CLAUDE.md` and `SPEC.md` in full before doing anything else. They are the source of truth.

Build **v1 only** (SPEC §2–§10). v2–v4 in §11 are context so your design doesn't block them. Do not implement them.

The most important rule: **the engine analyzes, the LLM explains.** Stockfish judges moves, python-chess detectors label mistakes, and Claude only explains the data it's given. Claude must never calculate or invent moves, and the backend validates every move it mentions (SPEC §7.4).

How I want to work:
- Start with milestone M0: write an implementation plan covering every v1 milestone in SPEC §10, including the data models and the main interfaces between modules. List anything in the spec that's ambiguous or that you'd change, with your recommendation. Then stop and wait for my approval.
- Work through the milestones in order. Stop at every ✅ checkpoint, show me evidence (test output, and sample analysis or coach output on real games where the milestone calls for it), and wait for my go-ahead.
- Commit after each working step with a clear message.
- Write tests alongside code. Keep `uv run pytest`, `ruff`, `mypy`, `npm test`, and `npm run lint` passing.
- Also stop and ask before adding a dependency not listed in CLAUDE.md, changing an approved schema, or making a decision the spec doesn't cover.
- If you learn a command or convention while working, update CLAUDE.md.

Things to verify rather than assume: the current `stockfish` npm package API and build names, the Lichess win% and accuracy constants in SPEC §6.1, and current Claude model IDs and prompt-caching syntax in Anthropic's docs.

Begin with M0.
