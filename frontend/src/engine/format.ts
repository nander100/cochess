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
