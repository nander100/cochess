import type { Color } from '../api/types'

interface EvalBarProps {
  /** White's win%, 0..100; null when the position hasn't been evaluated. */
  winPct: number | null
  /** Display eval, "+1.2" / "-M3". */
  evalText: string | null
  /** The board's orientation: that side's share is at the bottom, like Lichess. */
  orientation: Color
}

/** A vertical bar beside the board showing who's better in the position on the board. */
export function EvalBar({ winPct, evalText, orientation }: EvalBarProps) {
  const white = winPct ?? 50
  const bottom = orientation === 'white' ? white : 100 - white
  return (
    <div
      className={`eval-bar${winPct === null ? ' unknown' : ''}${orientation === 'black' ? ' flipped' : ''}`}
      role="meter"
      aria-label="Evaluation"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(white)}
      aria-valuetext={evalText ?? 'not evaluated'}
    >
      <div className="eval-bar-bottom" style={{ height: `${bottom}%` }} />
      <span className="eval-bar-text">{evalText ?? '–'}</span>
    </div>
  )
}
