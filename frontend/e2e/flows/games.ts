// Games for the end-to-end flows. The scripted engine scores material, so a hung piece is a real
// error: White's 3. Ng5?? loses the knight to the queen, which makes a critical moment.
export const HUNG_KNIGHT = `[Event "E2E"]
[White "Player"]
[Black "Opponent"]
[Result "0-1"]
[Date "2026.10.01"]
[TimeControl "600"]

1. e4 e5 2. Nf3 Nc6 3. Ng5 Qxg5 4. Nc3 Nf6 5. d3 Qg6 6. Be2 Bc5 0-1`

/** A short decisive rapid game against opponent `n` (distinct for each n). */
export function rapidGame(n: number, color: 'white' | 'black', result: '1-0' | '0-1'): string {
  const [white, black] = color === 'white' ? ['e2e_player', `Opponent ${n}`] : [`Opponent ${n}`, 'e2e_player']
  return [
    `[White "${white}"]`,
    `[Black "${black}"]`,
    `[Result "${result}"]`,
    `[Date "2026.10.${String(n + 1).padStart(2, '0')}"]`,
    '[TimeControl "600"]',
    '',
    `1. d4 d5 2. c4 e6 3. Nc3 Nf6 ${result}`,
  ].join('\n')
}
