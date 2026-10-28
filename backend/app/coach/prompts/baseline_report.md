# Your task: the baseline report

The player has just finished onboarding: 12 games in their main time control, 3 wins and 3 losses with each color. `baseline.games` has a compact summary of each (`number`, date, opponent, color, result, opening, `opening_moves`, accuracy, error counts, and their worst `key_moments` with the engine's lines). `player.tendencies` and `player.accuracy_by_phase` / `accuracy_by_color` are across their analyzed games.

Write their baseline report in markdown, **400–600 words**, with these six sections as level-3 headings:

### Overview
Who they are as a player right now, in 3–4 sentences: overall accuracy, how White and Black compare, and the phase where they're strongest and weakest.

### Strengths
One or two real strengths, each with an example: the game (by opponent and date, e.g. "your win against X on 2026-10-24") and a move from that game's data.

### Three things to work on
The top 3, taken from `player.tendencies` (worst first). For each: what it is in plain words, how often it happened (from `games_seen` and `rate_per_game`), and one example from a game's `key_moments`, with the move and the evals before and after.

### Openings
What they play as White and as Black, from `opening` and `opening_moves`, and whether it's working: results and opening accuracy only. Don't recommend new lines or recite theory that isn't in the data.

### Your plan for the next 2–4 weeks
A short weekly plan (2–4 bullet points) built on the three things to work on, with puzzle themes from the allowed list.

### Your turn
One question inviting them to open one of the example games and step through its critical moments.

Name games by opponent and date, never by `number` alone or by id.
