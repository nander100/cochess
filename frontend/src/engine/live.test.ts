import { isGameOver, numberedSan, toLiveLines } from './live'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

test('numbers lines from the position, for either side to move', () => {
  expect(numberedSan(START, ['e2e4', 'e7e5', 'g1f3'])).toBe('1. e4 e5 2. Nf3')
  expect(numberedSan(AFTER_E4, ['e7e5', 'g1f3', 'b8c6'])).toBe('1... e5 2. Nf3 Nc6')
})

test('a line that turns illegal (stale) is cut where it stops making sense', () => {
  expect(numberedSan(START, ['e2e4', 'e2e4'])).toBe('1. e4')
})

test('live lines: White-POV evals, win% for the bar, SAN text, capped plies', () => {
  const lines = toLiveLines(
    AFTER_E4,
    [
      { depth: 18, multipv: 1, score: { kind: 'cp', value: -30 }, pv: ['e7e5', 'g1f3', 'b8c6'] },
      { depth: 18, multipv: 2, score: { kind: 'mate', value: -2 }, pv: ['c7c5'] },
    ],
    2,
  )

  // Black to move: a side-to-move score of -30 is +0.3 for White; mate -2 for Black is White mating.
  expect(lines).toEqual([
    { rank: 1, evalText: '+0.3', winPct: expect.closeTo(52.76, 1), text: '1... e5 2. Nf3' },
    { rank: 2, evalText: '+M2', winPct: 100, text: '1... c5' },
  ])
})

test('checkmate and stalemate are game over', () => {
  expect(isGameOver('rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3')).toBe(true)
  expect(isGameOver('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1')).toBe(true)
  expect(isGameOver(START)).toBe(false)
})
