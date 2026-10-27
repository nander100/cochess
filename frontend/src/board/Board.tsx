import { Chessground } from '@lichess-org/chessground'
import type { Api } from '@lichess-org/chessground/api'
import '@lichess-org/chessground/assets/chessground.base.css'
import '@lichess-org/chessground/assets/chessground.brown.css'
import '@lichess-org/chessground/assets/chessground.cburnett.css'
import { useEffect, useRef } from 'react'
import type { Color } from '../api/types'
import { boardConfig, isPromotion } from './rules'

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
}

/** The chessground board. chess.js supplies the legal moves; chessground only draws and drags. */
export function Board({ fen, orientation, lastMove, movable, onMove }: BoardProps) {
  const element = useRef<HTMLDivElement>(null)
  const api = useRef<Api | null>(null)
  // The latest callback, so chessground's handler (bound once per position) is never stale.
  const moveHandler = useRef(onMove)
  useEffect(() => {
    moveHandler.current = onMove
  }, [onMove])

  useEffect(() => {
    if (!element.current) return
    api.current = Chessground(element.current, { coordinates: true, animation: { duration: 150 } })
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

  return <div ref={element} className="board" data-fen={fen} />
}
