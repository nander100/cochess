import type { BoardMove } from '../board/Board'
import type { GraphPoint } from '../board/EvalGraph'
import { ROOT, type GameTree, type TreeNode, addMove, fromMoves, lineFrom } from '../board/tree'
import { fromUci, withVariations } from '../board/variations'
import type { GameDetail, MomentInfo } from '../api/types'
import { isUnsolved } from '../moments/moment'

// Pure helpers for the game page: positions, evaluations and the game tree.

/** A position's identity for matching stored engine results: FEN without the move counters. */
export function positionKey(fen: string): string {
  return fen.split(' ').slice(0, 4).join(' ')
}

export function storedByPosition(results: GameDetail['engine_results']): Map<string, GameDetail['engine_results'][number]> {
  return new Map(results.map((result) => [positionKey(result.fen), result]))
}

/** What the eval bar shows for the position on the board. */
export function positionEval(
  node: TreeNode,
  detail: GameDetail,
  stored: Map<string, GameDetail['engine_results'][number]>,
): { winPct: number | null; evalText: string | null } {
  if (node.mainline && node.id !== ROOT) return { winPct: node.winPctAfter, evalText: node.evalAfter }
  const best = stored.get(positionKey(node.fen))?.lines[0]
  if (node.id === ROOT) return { winPct: detail.start_win_pct, evalText: best?.eval ?? null }
  return { winPct: best?.win_pct ?? null, evalText: best?.eval ?? null }
}

export function graphPoints(detail: GameDetail): GraphPoint[] {
  if (detail.start_win_pct === null) return []
  const start: GraphPoint = { ply: 0, winPct: detail.start_win_pct, evalText: null, moveText: null, label: null, side: null }
  return [
    start,
    ...detail.moves.flatMap((move) =>
      move.win_pct_after === null
        ? []
        : [
            {
              ply: move.ply,
              winPct: move.win_pct_after,
              evalText: move.eval_after,
              moveText: `${move.move_number}${move.side === 'white' ? '.' : '...'} ${move.san}`,
              label: move.label,
              side: move.side,
            },
          ],
    ),
  ]
}

/** The mainline ply the position belongs to: its own, or where its variation left the game. */
export function branchPly(tree: GameTree, node: TreeNode): number {
  let walker: TreeNode | undefined = node
  while (walker && !walker.mainline) walker = walker.parent === null ? undefined : tree.nodes[walker.parent]
  return walker?.ply ?? 0
}

export function mainlineNode(tree: GameTree, ply: number): string {
  const line = lineFrom(tree, ROOT)
  return line[Math.min(ply, line.length - 1)].id
}

export function endOfLine(tree: GameTree, nodeId: string): string {
  const line = lineFrom(tree, nodeId)
  return line[line.length - 1].id
}

export function toUci(move: BoardMove): string {
  return `${move.from}${move.to}${move.promotion ?? ''}`
}

/** The game, then the saved variations; before the first save, finished moments' lines. */
export function initialTree(detail: GameDetail): GameTree {
  const game = fromMoves(detail.moves, detail.final_fen)
  if (detail.variations) return withVariations(game, detail.variations)
  return detail.moments.filter((m) => !isUnsolved(m)).reduce(withMomentLines, game)
}

/** A finished moment's tries and the engine's move, as variations from its position. */
export function withMomentLines(tree: GameTree, moment: MomentInfo): GameTree {
  const from = mainlineNode(tree, moment.ply - 1)
  const moves = [...moment.attempts.map((a) => a.uci), ...(moment.best_uci ? [moment.best_uci] : [])]
  return moves.reduce((acc, uci) => addMove(acc, from, fromUci(uci))?.tree ?? acc, tree)
}
