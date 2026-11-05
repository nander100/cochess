import { Chessground } from '@lichess-org/chessground'
import type { Api } from '@lichess-org/chessground/api'
import '@lichess-org/chessground/assets/chessground.base.css'
import '@lichess-org/chessground/assets/chessground.cburnett.css'
import { useEffect, useRef } from 'react'
import type { Color } from '../api/types'
import './board.css'
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
}

/** The chessground board. chess.js supplies the legal moves; chessground only draws and drags. */
export function Board({ fen, orientation, lastMove, movable, onMove, sound = false }: BoardProps) {
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
