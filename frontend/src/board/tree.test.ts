import { DETAIL } from '../test/fakes'
import {
  type GameTree,
  ROOT,
  START_FEN,
  addMove,
  fromMoves,
  lineFrom,
  mainlineAt,
  next,
  pathTo,
  previous,
} from './tree'

const tree = fromMoves(DETAIL.moves, DETAIL.final_fen)

test('the mainline has one node per ply, ids are UCI paths, and the analysis is attached', () => {
  const last = mainlineAt(tree, 6)!

  expect(Object.keys(tree.nodes)).toHaveLength(7) // the start + 6 plies
  expect(tree.nodes[ROOT].fen).toBe(START_FEN)
  expect(pathTo(last)).toEqual(['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6'])
  expect(tree.nodes[last].fen).toBe(DETAIL.final_fen)
  expect(tree.nodes[mainlineAt(tree, 3)!]).toMatchObject({
    san: 'Nf3',
    ply: 3,
    mainline: true,
    label: 'mistake',
    evalAfter: '-1.0',
    winPctAfter: 30,
  })
  expect(tree.nodes[mainlineAt(tree, 1)!].fen).toBe(DETAIL.moves[1].fen_before)
})

test('a new move becomes a variation after the mainline child', () => {
  const afterE5 = mainlineAt(tree, 2)!

  const result = addMove(tree, afterE5, { from: 'f1', to: 'c4' })!

  expect(result.nodeId).toBe('e2e4 e7e5 f1c4')
  const node = result.tree.nodes[result.nodeId]
  expect(node).toMatchObject({ san: 'Bc4', uci: 'f1c4', ply: 3, mainline: false, label: null })
  expect(result.tree.nodes[afterE5].children).toEqual(['e2e4 e7e5 g1f3', 'e2e4 e7e5 f1c4'])
  expect(tree.nodes[afterE5].children).toEqual(['e2e4 e7e5 g1f3']) // the old tree is unchanged
})

test('replaying a move that is already in the tree reuses its node', () => {
  const afterE5 = mainlineAt(tree, 2)!

  const result = addMove(tree, afterE5, 'Nf3')!

  expect(result.nodeId).toBe(mainlineAt(tree, 3))
  expect(result.tree).toBe(tree)
})

test('variations can branch from variations, and continue a line', () => {
  const first = addMove(tree, mainlineAt(tree, 2)!, 'Bc4')!
  const second = addMove(first.tree, first.nodeId, 'Nf6')!
  const third = addMove(second.tree, first.nodeId, 'Bc5')!

  expect(pathTo(second.nodeId)).toEqual(['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  expect(third.tree.nodes[first.nodeId].children).toEqual([second.nodeId, third.nodeId])
  expect(lineFrom(third.tree, first.nodeId).map((n) => n.san)).toEqual(['Bc4', 'Nf6'])
})

test('an illegal move is refused', () => {
  expect(addMove(tree, ROOT, { from: 'e2', to: 'e5' })).toBeNull()
  expect(addMove(tree, ROOT, 'Nf6')).toBeNull() // Black can't move first
  expect(addMove(tree, 'no such node', 'e4')).toBeNull()
})

test('promotion is part of the UCI move', () => {
  const fen = '8/P7/8/8/8/8/8/k6K w - - 0 1'
  const promotion: GameTree = { nodes: { [ROOT]: { ...tree.nodes[ROOT], fen, children: [] } } }

  const result = addMove(promotion, ROOT, { from: 'a7', to: 'a8', promotion: 'n' })!

  expect(result.nodeId).toBe('a7a8n')
  expect(result.tree.nodes[result.nodeId].san).toBe('a8=N')
})

test('arrow-key navigation: back to the parent, forward along the first child', () => {
  const variation = addMove(tree, mainlineAt(tree, 2)!, 'Bc4')!

  expect(previous(variation.tree, variation.nodeId)).toBe(mainlineAt(tree, 2))
  expect(next(variation.tree, mainlineAt(tree, 2)!)).toBe(mainlineAt(tree, 3)) // mainline first
  expect(previous(tree, ROOT)).toBe(ROOT)
  expect(next(tree, mainlineAt(tree, 6)!)).toBe(mainlineAt(tree, 6))
})

test('mainlineAt is null past the end of the game', () => {
  expect(mainlineAt(tree, 0)).toBe(ROOT)
  expect(mainlineAt(tree, 7)).toBeNull()
})
