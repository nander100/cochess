import type { ReactNode } from 'react'
import './Pill.css'

export type PillTone = 'analyzed' | 'busy' | 'neutral' | 'good' | 'inaccuracy' | 'mistake' | 'blunder' | 'plan'

/** Status pill ("Analyzed", "Analyzing…") and chess-meaning pills. Chess meanings always carry a
 * glyph or a word as well as the color (tokens.md). */
export function Pill({ tone = 'neutral', children }: { tone?: PillTone; children: ReactNode }) {
  return <span className={`ui-pill ui-pill-${tone}`}>{children}</span>
}

/** A 12px square next to "White" or "Black". */
export function ColorSwatch({ color }: { color: 'white' | 'black' }) {
  return <span aria-hidden="true" className={`ui-swatch ui-swatch-${color}`} />
}
