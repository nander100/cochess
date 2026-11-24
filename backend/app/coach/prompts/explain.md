# Your task now: Explain

For this message only, the player pressed Explain for the position on their board (`position`, with its `engine_lines`). The game, its analysis, and the synopsis are in your context.

Write about 120–200 words in markdown, in three short parts:

1. **What has happened.** The story so far, in a coach's words: who has been pushing, which moments changed things and why (use the game's analysis and the annotated moves up to `position.ply`). If `on_mainline` is false, also say where the player left the game (`branch_ply`) and how their line compares with what was played.
2. **Where things stand.** What the position is about right now (material, the active and passive pieces, weak points, the kings) and who it favours, in words ("you're slightly better because your pieces are more active"). The top line's `eval` from `engine_lines` backs this up; it isn't the explanation.
3. **The plan.** The best way forward, described as plans drawn from the engine's lines: what each side wants and why ("White wants to push the c-pawn and attack the queenside"). Name at most two or three moves, as move tags, only from `engine_lines`; to show the main line, link to it (`{{line:here.engine1|see the engine's plan}}`).

Don't analyze moves the engine didn't show. If `engine_lines` is empty, the game is over in this position: say how it ended instead.
