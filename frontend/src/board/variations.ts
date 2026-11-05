import type { SavedVariation } from '../api/types'
import type { BoardMove } from './Board'
import { type GameTree, ROOT, type TreeNode, addMove, lineFrom, pathTo } from './tree'

/**
 * Saved variations (SPEC_V3 §5.1). The tree is the source of truth: a variation is every
 * explored line that leaves its parent's line, stored as the path it starts from plus its moves.
 * Their order in the list is their order in the tree, so display order survives a reload.
 */

/** A node begins a saved variation: it's explored, and doesn't simply continue the line its
 * parent is on (a parent in the game, or not the parent's first child). */
export function startsVariation(tree: GameTree, node: TreeNode): boolean {
  if (node.mainline || node.parent === null) return false
  const parent = tree.nodes[node.parent]
  return parent.mainline || parent.children[0] !== node.id
}

/** The tree's variations, parents before the variations that branch from them. */
export function variationsOf(tree: GameTree): SavedVariation[] {
  const found: SavedVariation[] = []
  const visit = (id: string) => {
    const node = tree.nodes[id]
    for (const child of node.children) {
      if (startsVariation(tree, tree.nodes[child])) {
        found.push({ start_path: pathTo(id), moves: lineFrom(tree, child).map((n) => n.uci ?? '') })
      }
    }
    node.children.forEach(visit)
  }
  visit(ROOT)
  return found
}

/** Play each variation into the tree, in order. A move that isn't legal ends that line (the
 * backend checked them when they were saved). */
export function withVariations(tree: GameTree, variations: readonly SavedVariation[]): GameTree {
  return variations.reduce((acc, v) => withLine(acc, [...v.start_path, ...v.moves]), tree)
}

/** Follow `path` (UCI) from the start, adding any moves not already in the tree. */
export function withLine(tree: GameTree, path: readonly string[]): GameTree {
  let current = tree
  let at = ROOT
  for (const uci of path) {
    const played = addMove(current, at, fromUci(uci))
    if (!played) break
    current = played.tree
    at = played.nodeId
  }
  return current
}

/** Remove the variation starting at `startId`, with everything that branches from it. */
export function deleteVariation(tree: GameTree, startId: string): GameTree {
  const start = tree.nodes[startId]
  if (!start || start.parent === null || start.mainline) return tree
  const parent = tree.nodes[start.parent]
  const nodes = Object.fromEntries(
    Object.entries(tree.nodes).filter(([id]) => !isWithin(id, startId)),
  )
  nodes[parent.id] = { ...parent, children: parent.children.filter((c) => c !== startId) }
  return { nodes }
}

/** Where promoting puts a variation among its parent's moves: first, except that the game's own
 * move always stays first (SPEC_V3 §5.1: display order only, never the actual game). */
function promotedIndex(tree: GameTree, parent: TreeNode): number {
  const first = tree.nodes[parent.children[0]]
  return parent.mainline && first?.mainline ? 1 : 0
}

export function canPromote(tree: GameTree, startId: string): boolean {
  const node = tree.nodes[startId]
  if (!node || node.parent === null || node.mainline) return false
  const parent = tree.nodes[node.parent]
  return parent.children.indexOf(startId) > promotedIndex(tree, parent)
}

/** Move the variation to the front of the lines at its branch point. Inside another variation it
 * becomes that line's continuation, and the old continuation becomes a variation. */
export function promoteVariation(tree: GameTree, startId: string): GameTree {
  if (!canPromote(tree, startId)) return tree
  const parent = tree.nodes[tree.nodes[startId].parent ?? ROOT]
  const others = parent.children.filter((c) => c !== startId)
  const index = promotedIndex(tree, parent)
  const children = [...others.slice(0, index), startId, ...others.slice(index)]
  return { nodes: { ...tree.nodes, [parent.id]: { ...parent, children } } }
}

/** The start of the variation that `nodeId` is in (null in the game itself). */
export function variationStart(tree: GameTree, nodeId: string): string | null {
  let node: TreeNode | undefined = tree.nodes[nodeId]
  while (node && !node.mainline) {
    if (startsVariation(tree, node)) return node.id
    node = node.parent === null ? undefined : tree.nodes[node.parent]
  }
  return null
}

/** Node ids are paths, so a node is within a line exactly when its path extends the line's. */
export function isWithin(nodeId: string, startId: string): boolean {
  return nodeId === startId || nodeId.startsWith(`${startId} `)
}

/** A UCI move ("e7e8q") as the board describes moves. */
export function fromUci(uci: string): BoardMove {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), ...(uci.length > 4 ? { promotion: uci[4] } : {}) }
}
