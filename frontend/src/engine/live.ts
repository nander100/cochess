import { Chess } from 'chess.js'
import { formatEval, winPercent } from './format'
import { toWhitePov } from './score'
import type { InfoLine } from './uci'

/** One line of the live engine panel, ready to show. Display only: never posted anywhere. */
export interface LiveLine {
  rank: number
  /** "+0.4" / "-M3", White's point of view. */
  evalText: string
  /** White's win%, for the eval bar. */
  winPct: number
  /** The line in SAN with move numbers: "14. Nf3 Nc6 15. Bb5". */
  text: string
}

/** The engine's lines for `fen` as the panel shows them, at most `maxPlies` moves each. */
export function toLiveLines(fen: string, lines: readonly InfoLine[], maxPlies: number): LiveLine[] {
  return lines.map((line, index) => {
    const score = toWhitePov(fen, line.score)
    return {
      rank: index + 1,
      evalText: formatEval(score),
      winPct: winPercent(score),
      text: numberedSan(fen, line.pv.slice(0, maxPlies)),
    }
  })
}

/** "14. Nf3 Nc6 15. Bb5" (or "14... Nc6 15. Bb5" when Black is to move), stopping at an illegal move. */
export function numberedSan(fen: string, uciMoves: readonly string[]): string {
  const chess = new Chess(fen)
  const parts: string[] = []
  for (const [index, uci] of uciMoves.entries()) {
    const white = chess.turn() === 'w'
    const number = chess.moveNumber()
    let san: string
    try {
      san = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }).san
    } catch {
      break // a stale line from the previous position: show what's valid
    }
    if (white) parts.push(`${number}. ${san}`)
    else parts.push(index === 0 ? `${number}... ${san}` : san)
  }
  return parts.join(' ')
}

/** Checkmate or stalemate: the engine can't search it. */
export function isGameOver(fen: string): boolean {
  return new Chess(fen).moves().length === 0
}
