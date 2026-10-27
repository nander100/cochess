import { type MouseEvent, useState } from 'react'
import type { Color, MoveLabel } from '../api/types'

export interface GraphPoint {
  /** 0 = the starting position; n = after ply n. */
  ply: number
  /** White's win%, 0..100. */
  winPct: number
  /** Display eval, "+1.2" / "-M3"; null at the start. */
  evalText: string | null
  /** "12. Nf3" / "12... Nf6"; null at the start. */
  moveText: string | null
  label: MoveLabel | null
  side: Color | null
}

interface EvalGraphProps {
  points: readonly GraphPoint[]
  userColor: Color
  /** The ply shown on the board, if it's on the mainline. */
  currentPly: number | null
  onSelectPly: (ply: number) => void
}

const WIDTH = 600
const HEIGHT = 120
const DOT_LABELS: readonly MoveLabel[] = ['inaccuracy', 'mistake', 'blunder', 'missed_mate']

/**
 * White's win% over the game (SPEC_V2 §5.4). Win%, not centipawns, so mates don't spike off the
 * chart. Hover shows the move and eval; click jumps there. Plain SVG, no chart library.
 */
export function EvalGraph({ points, userColor, currentPly, onSelectPly }: EvalGraphProps) {
  const [hovered, setHovered] = useState<GraphPoint | null>(null)
  if (points.length < 2) return null
  const last = points[points.length - 1].ply
  const x = (ply: number) => (ply / last) * WIDTH
  const y = (winPct: number) => ((100 - winPct) / 100) * HEIGHT
  const curve = points.map((p) => `${x(p.ply).toFixed(1)},${y(p.winPct).toFixed(1)}`).join(' ')

  function pointAt(event: MouseEvent<SVGSVGElement>): GraphPoint {
    const box = event.currentTarget.getBoundingClientRect()
    const fraction = box.width > 0 ? (event.clientX - box.left) / box.width : 0
    const ply = Math.round(Math.min(1, Math.max(0, fraction)) * last)
    return points.find((p) => p.ply === ply) ?? points[0]
  }

  const mistakes = points.filter(
    (p) => p.label !== null && p.side === userColor && DOT_LABELS.includes(p.label),
  )
  return (
    <figure className="eval-graph">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Evaluation graph: White's winning chances move by move"
        onMouseMove={(event) => setHovered(pointAt(event))}
        onMouseLeave={() => setHovered(null)}
        onClick={(event) => onSelectPly(pointAt(event).ply)}
      >
        <rect className="eval-graph-black" width={WIDTH} height={HEIGHT} />
        <polygon className="eval-graph-white" points={`0,${HEIGHT} ${curve} ${WIDTH},${HEIGHT}`} />
        <line className="eval-graph-mid" x1={0} x2={WIDTH} y1={HEIGHT / 2} y2={HEIGHT / 2} />
        <polyline className="eval-graph-line" points={curve} />
        {currentPly !== null && (
          <line className="eval-graph-current" x1={x(currentPly)} x2={x(currentPly)} y1={0} y2={HEIGHT} />
        )}
        {hovered && (
          <line className="eval-graph-hover" x1={x(hovered.ply)} x2={x(hovered.ply)} y1={0} y2={HEIGHT} />
        )}
        {mistakes.map((p) => (
          <circle
            key={p.ply}
            className={`eval-graph-dot ${p.label}`}
            cx={x(p.ply)}
            cy={y(p.winPct)}
            r={4}
            data-ply={p.ply}
          />
        ))}
      </svg>
      <figcaption className="eval-graph-caption" aria-live="polite">
        {hovered ? describe(hovered) : 'Hover to see the evaluation; click to jump to a move.'}
      </figcaption>
    </figure>
  )
}

function describe(point: GraphPoint): string {
  if (point.moveText === null) return 'Start of the game'
  return `${point.moveText}: ${point.evalText ?? '?'}`
}
