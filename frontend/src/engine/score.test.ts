import { toWhitePov } from './score'

const WHITE_TO_MOVE = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const BLACK_TO_MOVE = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

test('keeps scores when White is to move', () => {
  expect(toWhitePov(WHITE_TO_MOVE, { kind: 'cp', value: 35 })).toEqual({ eval_cp: 35, mate: null })
  expect(toWhitePov(WHITE_TO_MOVE, { kind: 'mate', value: 2 })).toEqual({ eval_cp: null, mate: 2 })
})

test('flips scores when Black is to move', () => {
  expect(toWhitePov(BLACK_TO_MOVE, { kind: 'cp', value: 35 })).toEqual({ eval_cp: -35, mate: null })
  expect(toWhitePov(BLACK_TO_MOVE, { kind: 'mate', value: -4 })).toEqual({ eval_cp: null, mate: 4 })
})

test('rejects mate 0, which has no sign', () => {
  expect(() => toWhitePov(WHITE_TO_MOVE, { kind: 'mate', value: 0 })).toThrow(/mate 0/)
})

test('rejects a FEN without a side to move', () => {
  expect(() => toWhitePov('8/8/8/8/8/8/8/8', { kind: 'cp', value: 0 })).toThrow(/Invalid FEN/)
})
