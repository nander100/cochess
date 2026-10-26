import type { UciScore } from './uci'

export interface WhitePovScore {
  eval_cp: number | null
  mate: number | null
}

/**
 * The one place a side-to-move engine score is converted to White's point of view
 * (CLAUDE.md conventions, PLAN Q4). The backend never converts again.
 */
export function toWhitePov(fen: string, score: UciScore): WhitePovScore {
  const sideToMove = fen.split(' ')[1]
  if (sideToMove !== 'w' && sideToMove !== 'b') {
    throw new Error(`Invalid FEN (no side to move): ${fen}`)
  }
  if (score.kind === 'mate' && score.value === 0) {
    throw new Error('mate 0 has no sign; terminal positions must not be searched')
  }
  const sign = sideToMove === 'w' ? 1 : -1
  return score.kind === 'cp'
    ? { eval_cp: sign * score.value, mate: null }
    : { eval_cp: null, mate: sign * score.value }
}
