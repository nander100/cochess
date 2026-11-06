import { Chessground } from '@lichess-org/chessground'
import type { Api } from '@lichess-org/chessground/api'
import type { DrawBrushes } from '@lichess-org/chessground/draw'
import '@lichess-org/chessground/assets/chessground.base.css'
import '@lichess-org/chessground/assets/chessground.cburnett.css'
import { useEffect, useRef } from 'react'
import type { Annotation, Color } from '../api/types'
import { useTheme } from '../theme/themeContext'
import './board.css'
import { coachBrushes, toShapes } from './coachShapes'
import { boardConfig, isPromotion } from './rules'
import { playMoveSound } from './sound'

export interface BoardMove {
  from: string
  to: string
  promotion?: string
}

interface BoardProps {
  fen: string
  orientation: Color
  /** The move that led to this position, as UCI (e.g. "e2e4"), to highlight it. */
  lastMove: string | null
  /** When false, pieces can't be moved. */
  movable: boolean
  onMove: (move: BoardMove) => void
  /** Play a short sound when a move appears on the board (Settings: sounds on move). */
  sound?: boolean
  /** The coach's checked arrows and highlights for this position (SPEC_V3 §6.3). Drawn as
   * chessground auto-shapes, so the player's own right-click drawings stay separate. */
  annotations?: readonly Annotation[]
}

const NO_ANNOTATIONS: readonly Annotation[] = []

/** The chessground board. chess.js supplies the legal moves; chessground only draws and drags. */
export function Board({
  fen, orientation, lastMove, movable, onMove, sound = false, annotations = NO_ANNOTATIONS,
}: BoardProps) {
  const element = useRef<HTMLDivElement>(null)
  const api = useRef<Api | null>(null)
  // The latest callback, so chessground's handler (bound once per position) is never stale.
  const moveHandler = useRef(onMove)
  useEffect(() => {
    moveHandler.current = onMove
  }, [onMove])

  useEffect(() => {
    if (!element.current) return
    // Reduced motion (SPEC_V3 §4.5): pieces jump instead of sliding.
    const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    api.current = Chessground(element.current, { coordinates: true, animation: { enabled: !reduce, duration: 150 } })
    return () => {
      api.current?.destroy()
      api.current = null
    }
  }, [])

  useEffect(() => {
    api.current?.set(
      boardConfig(fen, orientation, lastMove, movable, (from, to) => {
        moveHandler.current({ from, to, ...(isPromotion(fen, from, to) ? { promotion: 'q' } : {}) })
      }),
    )
  }, [fen, orientation, lastMove, movable])

  // The coach's shapes, in the current theme's chess-meaning colors.
  const { theme } = useTheme()
  useEffect(() => {
    // chessground deep-merges config, so this adds the coach brushes to its own four.
    api.current?.set({ drawable: { brushes: coachBrushes() as unknown as DrawBrushes } })
    api.current?.setAutoShapes(toShapes(annotations))
  }, [annotations, theme, fen])

  // A sound for each new move shown (not on first render, nor when only the orientation changes).
  const shownMove = useRef(lastMove)
  useEffect(() => {
    if (lastMove && lastMove !== shownMove.current && sound) playMoveSound()
    shownMove.current = lastMove
  }, [lastMove, sound])

  // The frame wraps chessground's element: chessground sizes the board from its own element's box,
  // so the border can't sit on that element.
  return (
    <div className="board-frame">
      <div ref={element} className="board" data-fen={fen} />
    </div>
  )
}
