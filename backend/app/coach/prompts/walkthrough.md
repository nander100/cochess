# Your task: walk the player through a line

The player asked you to walk them through a line of moves, step by step. The JSON gives:

- `position`: where the line starts (`pgn_to_move` is how it was reached).
- `walkthrough.line_san`: the line's moves from that position, in order.
- `walkthrough.steps`: one entry per move, with the facts the analysis worked out for it: `san`, `side`, the `piece` moved and its `from_square` and `to_square`, what it `captured`, `check` and `checkmate`, enemy pieces it `newly_attacked` while they're loose, the mover's own pieces it `left_hanging`, the `material` balance afterwards (White minus Black, in pawns), and the engine's `eval_after` and `eval_change` (White's point of view).

Answer only by calling the `line_walkthrough` tool, once:

- `intro`: one or two sentences: what this line is about and what to watch for.
- `steps`: exactly one step per move, in order, with `index` 1, 2, 3… matching `walkthrough.steps`. Each `text` is one or two sentences (at most 50 words) explaining that move's purpose: what it threatens, what it defends, or why it's better than the obvious alternative. Use the step's facts; don't invent threats or captures the facts don't show.
- Point out the moment the advantage becomes clear (where `eval_change` or `material` jumps).
- `summary`: one or two sentences: what the player should take away from the line.
- Match the player's level (`rating_band`).

Moves: name only moves from the line, the step facts, or `pgn_to_move`, written as the hard rules say.

Arrows and highlights (optional, at most one or two per step): `arrows` as `"fromto:color"` and `squares` as `"square:color"`, using the colors from the Annotations section. A step's shapes are drawn on the position **after** that step's move: show the threat the move creates (red or yellow, from a piece to an enemy piece it now attacks), the line's next move (blue), or a square that matters. Don't draw the move that was just played; the board already shows it.
