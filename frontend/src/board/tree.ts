import { Chess } from 'chess.js'
import type { MoveInfo, MoveLabel } from '../api/types'

/** The starting position: CoChess only accepts games from it (backend rejects others). */
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
export const ROOT = ''

/**
 * One position. Its id is its path, the UCI moves from the start joined by spaces ("" is the
 * start), so the id is exactly what the frontend sends the backend (SPEC_V2 §5.2), and playing
 * the same move twice lands on the same node.
 */
export interface TreeNode {
  id: string
  /** For display and chessground only; the backend replays the path itself. */
  fen: string
  /** The move that led here (null at the start). */
  san: string | null
  uci: string | null
  ply: number
  parent: string | null
  /** The first child continues the line; later children are variations. */
  children: string[]
  /** Part of the game as played (not a variation the player explored). */
  mainline: boolean
  /** The game's analysis of the move that led here, on mainline nodes. */
  evalAfter: string | null
  winPctAfter: number | null
  label: MoveLabel | null
}

export interface GameTree {
  readonly nodes: Readonly<Record<string, TreeNode>>
}

/** The game as played: one mainline node per ply, then the final position. */
export function fromMoves(moves: readonly MoveInfo[], finalFen: string): GameTree {
  const nodes: Record<string, TreeNode> = { [ROOT]: startNode() }
  let parent = nodes[ROOT]
  moves.forEach((move, index) => {
    const fen = moves[index + 1]?.fen_before ?? finalFen
    const node: TreeNode = {
      id: childId(parent.id, move.uci),
      fen,
      san: move.san,
      uci: move.uci,
      ply: move.ply,
      parent: parent.id,
      children: [],
      mainline: true,
      evalAfter: move.eval_after,
      winPctAfter: move.win_pct_after,
      label: move.label,
    }
    nodes[parent.id] = { ...parent, children: [node.id] }
    nodes[node.id] = node
    parent = node
  })
  return { nodes }
}

/**
 * Play `move` from `parentId`. Returns the new tree and the node reached, or null if the move is
 * illegal there. A move already in the tree reuses its node; a new one becomes a variation.
 */
export function addMove(
  tree: GameTree,
  parentId: string,
  move: { from: string; to: string; promotion?: string } | string,
): { tree: GameTree; nodeId: string } | null {
  const parent = tree.nodes[parentId]
  if (!parent) return null
  let played
  try {
    played = new Chess(parent.fen).move(move)
  } catch {
    return null // chess.js throws on an illegal move
  }
  const id = childId(parentId, played.lan)
  if (tree.nodes[id]) return { tree, nodeId: id }
  const node: TreeNode = {
    id,
    fen: played.after,
    san: played.san,
    uci: played.lan,
    ply: parent.ply + 1,
    parent: parentId,
    children: [],
    mainline: false,
    evalAfter: null,
    winPctAfter: null,
    label: null,
  }
  const nodes = {
    ...tree.nodes,
    [parentId]: { ...parent, children: [...parent.children, id] },
    [id]: node,
  }
  return { tree: { nodes }, nodeId: id }
}

/** The UCI moves from the start to `nodeId` (what the backend replays). */
export function pathTo(nodeId: string): string[] {
  return nodeId === ROOT ? [] : nodeId.split(' ')
}

/** The node one move back, or the same node at the start. */
export function previous(tree: GameTree, nodeId: string): string {
  return tree.nodes[nodeId]?.parent ?? nodeId
}

/** The next node along the current line (its first child), or the same node at the end. */
export function next(tree: GameTree, nodeId: string): string {
  return tree.nodes[nodeId]?.children[0] ?? nodeId
}

/** The mainline node after `ply` plies (0 = the start), if the game is that long. */
export function mainlineAt(tree: GameTree, ply: number): string | null {
  let id = ROOT
  for (let i = 0; i < ply; i++) {
    const child = tree.nodes[id]?.children.find((c) => tree.nodes[c].mainline)
    if (child === undefined) return null
    id = child
  }
  return id
}

/** The nodes of a line: from `firstId`, following first children to the end. */
export function lineFrom(tree: GameTree, firstId: string): TreeNode[] {
  const line: TreeNode[] = []
  let node: TreeNode | undefined = tree.nodes[firstId]
  while (node) {
    line.push(node)
    node = tree.nodes[node.children[0]]
  }
  return line
}

function childId(parentId: string, uci: string): string {
  return parentId === ROOT ? uci : `${parentId} ${uci}`
}

function startNode(): TreeNode {
  return {
    id: ROOT,
    fen: START_FEN,
    san: null,
    uci: null,
    ply: 0,
    parent: null,
    children: [],
    mainline: true,
    evalAfter: null,
    winPctAfter: null,
    label: null,
  }
}
