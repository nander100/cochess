import type { MoveInfo } from '../api/types'
import { ROOT, addMove, fromMoves, type GameTree } from './tree'
import {
  canPromote,
  deleteVariation,
  promoteVariation,
  variationStart,
  variationsOf,
  withLine,
  withVariations,
} from './variations'

function move(ply: number, san: string, uci: string): MoveInfo {
  return {
    ply, move_number: Math.floor((ply + 1) / 2), side: ply % 2 === 1 ? 'white' : 'black', san, uci,
    fen_before: '', clock_s: null, eval_after: null, win_pct_after: null, label: null,
  } // prettier-ignore
}

// 1. e4 e5 2. Nf3: fen_before is only used for display, so the game is rebuilt by playing it.
function game(): GameTree {
  const played = withLine(fromMoves([], 'unused'), ['e2e4', 'e7e5', 'g1f3'])
  const moves = [move(1, 'e4', 'e2e4'), move(2, 'e5', 'e7e5'), move(3, 'Nf3', 'g1f3')]
  const mainline = fromMoves(moves, played.nodes['e2e4 e7e5 g1f3'].fen)
  // Give the mainline nodes their real positions so moves can be played from them.
  const nodes = { ...mainline.nodes }
  for (const id of Object.keys(nodes)) nodes[id] = { ...nodes[id], fen: played.nodes[id].fen }
  return { nodes }
}

const AFTER_E5 = 'e2e4 e7e5'

test('a game with no explored moves has no variations', () => {
  expect(variationsOf(game())).toEqual([])
})

test('explored lines are saved as a start path and moves, parents first', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'f8c5']) // branches inside the first line
  tree = withLine(tree, ['d2d4']) // from the start
  tree = withLine(tree, ['e2e4', 'e7e5', 'g1f3', 'b8c6']) // past the end of the game

  expect(variationsOf(tree)).toEqual([
    { start_path: [], moves: ['d2d4'] },
    { start_path: ['e2e4', 'e7e5'], moves: ['f1c4', 'g8f6'] },
    { start_path: ['e2e4', 'e7e5', 'g1f3'], moves: ['b8c6'] },
    { start_path: ['e2e4', 'e7e5', 'f1c4'], moves: ['f8c5'] },
  ])
})

test('saved variations rebuild the same tree, in the same order', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'b1c3'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'f8c5'])

  const rebuilt = withVariations(game(), variationsOf(tree))

  expect(rebuilt.nodes[AFTER_E5].children).toEqual(tree.nodes[AFTER_E5].children)
  expect(variationsOf(rebuilt)).toEqual(variationsOf(tree))
})

test('an illegal saved move ends that line without breaking the rest', () => {
  const tree = withVariations(game(), [
    { start_path: ['e2e4'], moves: ['e7e5', 'e1e3'] },
    { start_path: [], moves: ['d2d4'] },
  ])

  expect(variationsOf(tree)).toEqual([{ start_path: [], moves: ['d2d4'] }])
})

test('deleting a variation removes it and what branches from it', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'f8c5'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'b1c3'])

  const after = deleteVariation(tree, 'e2e4 e7e5 f1c4')

  expect(variationsOf(after)).toEqual([{ start_path: ['e2e4', 'e7e5'], moves: ['b1c3'] }])
  expect(after.nodes['e2e4 e7e5 f1c4 f8c5']).toBeUndefined()
  expect(deleteVariation(tree, 'e2e4')).toBe(tree) // the game itself can't be deleted
})

test('promoting off the game puts the line first among the alternatives, never before the game move', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'f1c4'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'b1c3'])
  expect(canPromote(tree, 'e2e4 e7e5 f1c4')).toBe(false)
  expect(canPromote(tree, 'e2e4 e7e5 b1c3')).toBe(true)

  const after = promoteVariation(tree, 'e2e4 e7e5 b1c3')

  expect(after.nodes[AFTER_E5].children).toEqual(['e2e4 e7e5 g1f3', 'e2e4 e7e5 b1c3', 'e2e4 e7e5 f1c4'])
  expect(canPromote(after, 'e2e4 e7e5 b1c3')).toBe(false)
  expect(canPromote(after, 'e2e4 e7e5 g1f3')).toBe(false)
})

test('promoting inside a variation makes it the continuation', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'f8c5'])

  const after = promoteVariation(tree, 'e2e4 e7e5 f1c4 f8c5')

  expect(variationsOf(after)).toEqual([
    { start_path: ['e2e4', 'e7e5'], moves: ['f1c4', 'f8c5'] },
    { start_path: ['e2e4', 'e7e5', 'f1c4'], moves: ['g8f6'] },
  ])
})

test('every explored node knows the variation it belongs to', () => {
  let tree = withLine(game(), ['e2e4', 'e7e5', 'f1c4', 'g8f6'])
  tree = withLine(tree, ['e2e4', 'e7e5', 'f1c4', 'f8c5'])

  expect(variationStart(tree, 'e2e4 e7e5 f1c4 g8f6')).toBe('e2e4 e7e5 f1c4')
  expect(variationStart(tree, 'e2e4 e7e5 f1c4 f8c5')).toBe('e2e4 e7e5 f1c4 f8c5')
  expect(variationStart(tree, 'e2e4 e7e5')).toBeNull()
  expect(variationStart(tree, ROOT)).toBeNull()
})

test('a move already in the game is reused, not saved again', () => {
  const tree = addMove(game(), 'e2e4', { from: 'e7', to: 'e5' })?.tree ?? game()
  expect(variationsOf(tree)).toEqual([])
})
