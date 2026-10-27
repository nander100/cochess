# Your task: Explain

The player pressed Explain for the position on their board (`position`, with its `engine_lines`). The game, its analysis, and the synopsis are in your context.

Write about 120–200 words in markdown, in three short parts:

1. **What has happened.** How the game reached this position: the key moments up to this ply and how the evaluation moved (use the game's analysis and the annotated moves up to `position.ply`). If `on_mainline` is false, also say where the player left the game (`branch_ply`) and how their line compares with what was played.
2. **Where things stand.** The evaluation from `engine_lines` (the top line's `eval`), and what it means in words for the player ("you're slightly better", "Black is winning").
3. **The plan.** The best way forward, described as plans drawn from the engine's lines: what each side wants and why ("White wants to push the c-pawn and attack the queenside"). Name at most two or three moves, only from `engine_lines`.

Don't analyze moves the engine didn't show. If `engine_lines` is empty, the game is over in this position: say how it ended instead.
