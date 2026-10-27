import type { EngineLine } from '../api/types'

/** Same display format as the backend's format_eval: +0.3, -2.0, 0.0, +M3, -M2. */
export function formatEval(line: Pick<EngineLine, 'eval_cp' | 'mate'>): string {
  if (line.mate !== null) return line.mate > 0 ? `+M${line.mate}` : `-M${-line.mate}`
  const pawns = Math.round((line.eval_cp ?? 0) / 10) / 10
  return pawns === 0 ? '0.0' : `${pawns > 0 ? '+' : ''}${pawns.toFixed(1)}`
}

/** "before 14." for White to move at ply 27, "before 14..." for Black at ply 28. */
export function positionLabel(ply: number | null, totalPlies: number): string {
  if (ply === null) return '—'
  if (ply > totalPlies) return 'final position'
  const move = Math.floor((ply + 1) / 2)
  return `before ${move}${ply % 2 === 1 ? '.' : '...'}`
}

/** Lichess winning-chances multiplier and centipawn ceiling (backend/app/analysis/evals.py). */
const WC_MULTIPLIER = -0.00368208
const CP_CEILING = 1000

/**
 * White's win%, 0..100: the backend's formula, mirrored for live engine lines only (stored results
 * arrive with win% computed by the backend). Mate is 100 or 0.
 */
export function winPercent(line: Pick<EngineLine, 'eval_cp' | 'mate'>): number {
  if (line.mate !== null) return line.mate > 0 ? 100 : 0
  const cp = Math.max(-CP_CEILING, Math.min(CP_CEILING, line.eval_cp ?? 0))
  return 50 + 50 * (2 / (1 + Math.exp(WC_MULTIPLIER * cp)) - 1)
}
