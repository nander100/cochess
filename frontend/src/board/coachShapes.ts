import type { DrawBrush, DrawShape } from '@lichess-org/chessground/draw'
import type { Key } from '@lichess-org/chessground/types'
import type { Annotation, AnnotationColor } from '../api/types'

/** The coach's arrows and highlights (SPEC_V3 §6.3) use their own brushes, so they never share
 * a brush with arrows the player draws (chessground's green/red/blue/yellow). */
export const COACH_BRUSH: Record<AnnotationColor, string> = {
  green: 'coachGreen',
  red: 'coachRed',
  yellow: 'coachYellow',
  blue: 'coachBlue',
}

// The shared chess-meaning colors (tokens.md): good, mistake or threat, inaccuracy, plan.
const TOKEN: Record<AnnotationColor, string> = {
  green: '--chess-good',
  red: '--chess-blunder',
  yellow: '--chess-inaccuracy',
  blue: '--chess-plan',
}
const KEY: Record<AnnotationColor, string> = { green: 'cg', red: 'cr', yellow: 'cy', blue: 'cb' }
const OPACITY = 1 // chessground already dims its shape layer (as on Lichess)
const LINE_WIDTH = 10

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** The coach brushes in the current theme's colors (read from the design tokens). */
export function coachBrushes(read: (name: string) => string = cssVar): Record<string, DrawBrush> {
  const colors = Object.keys(COACH_BRUSH) as AnnotationColor[]
  return Object.fromEntries(
    colors.map((color) => [
      COACH_BRUSH[color],
      { key: KEY[color], color: read(TOKEN[color]), opacity: OPACITY, lineWidth: LINE_WIDTH },
    ]),
  )
}

/** Arrows as arrows; a highlighted square as a circle on it (as on Lichess). */
export function toShapes(annotations: readonly Annotation[]): DrawShape[] {
  return annotations.flatMap((annotation) => [
    ...annotation.arrows.map((a) => ({ orig: a.orig as Key, dest: a.dest as Key, brush: COACH_BRUSH[a.color] })),
    ...annotation.squares.map((s) => ({ orig: s.square as Key, brush: COACH_BRUSH[s.color] })),
  ])
}

/** For each board position (node id), the annotations of the latest coach message about it: a
 * newer answer without tags clears what an older one drew there. */
export function latestByPath(
  messages: readonly { role: string; path?: string | null; annotations?: readonly Annotation[] }[],
): Map<string, Annotation[]> {
  const latest = new Map<string, Annotation[]>()
  for (const message of messages) {
    if (message.role === 'coach' && message.path != null) latest.set(message.path, [...(message.annotations ?? [])])
  }
  return latest
}
