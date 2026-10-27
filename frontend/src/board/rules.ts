import type { Config } from '@lichess-org/chessground/config'
import type { Key } from '@lichess-org/chessground/types'
import { Chess, type Square } from 'chess.js'
import type { Color } from '../api/types'

/** The chessground settings for a position: legal moves from chess.js, the last move, check. */
export function boardConfig(
  fen: string,
  orientation: Color,
  lastMove: string | null,
  movable: boolean,
  after: (from: string, to: string) => void,
): Config {
  const chess = new Chess(fen)
  const turnColor = chess.turn() === 'w' ? 'white' : 'black'
  return {
    fen,
    orientation,
    turnColor,
    check: chess.inCheck(),
    lastMove: lastMove ? ([lastMove.slice(0, 2), lastMove.slice(2, 4)] as Key[]) : undefined,
    movable: {
      free: false,
      color: movable ? turnColor : undefined,
      dests: movable ? legalDests(chess) : new Map(),
      showDests: true,
      events: { after: (orig, dest) => after(orig, dest) },
    },
    premovable: { enabled: false },
    draggable: { enabled: movable },
  }
}

/** Every legal move as chessground wants it: from-square → destination squares. */
export function legalDests(chess: Chess): Map<Key, Key[]> {
  const dests = new Map<Key, Key[]>()
  for (const move of chess.moves({ verbose: true })) {
    const from = move.from as Key
    dests.set(from, [...(dests.get(from) ?? []), move.to as Key])
  }
  return dests
}

/** A pawn reaching the last rank. It promotes to a queen; under-promotion isn't offered in v2. */
export function isPromotion(fen: string, from: string, to: string): boolean {
  const piece = new Chess(fen).get(from as Square)
  return piece?.type === 'p' && (to[1] === '8' || to[1] === '1')
}
