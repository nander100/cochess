import { Chess } from 'chess.js'
import { boardConfig, isPromotion, legalDests } from './rules'
import { START_FEN } from './tree'

test('legal destinations for every piece that can move', () => {
  const dests = legalDests(new Chess(START_FEN))

  expect(dests.get('e2')).toEqual(['e3', 'e4'])
  expect(dests.get('g1')?.sort()).toEqual(['f3', 'h3'])
  expect(dests.has('e1')).toBe(false)
  expect([...dests.values()].flat()).toHaveLength(20)
})

test('the board config follows the position: side to move, check, last move', () => {
  const fen = 'rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3' // fool's mate

  const config = boardConfig(fen, 'black', 'd8h4', true, () => {})

  expect(config).toMatchObject({ fen, orientation: 'black', turnColor: 'white', check: true })
  expect(config.lastMove).toEqual(['d8', 'h4'])
  expect(config.movable?.dests?.size).toBe(0) // checkmate: nothing to move
})

test('a board that is not movable lets no one move', () => {
  const config = boardConfig(START_FEN, 'white', null, false, () => {})

  expect(config.movable?.color).toBeUndefined()
  expect(config.movable?.dests?.size).toBe(0)
  expect(config.draggable?.enabled).toBe(false)
})

test('the move callback receives chessground moves', () => {
  const after = vi.fn()
  const config = boardConfig(START_FEN, 'white', null, true, after)

  config.movable?.events?.after?.('e2', 'e4', { premove: false })

  expect(after).toHaveBeenCalledWith('e2', 'e4')
})

test('only a pawn reaching the last rank promotes', () => {
  const fen = '8/P6k/8/8/8/8/1p5K/R7 w - - 0 1'

  expect(isPromotion(fen, 'a7', 'a8')).toBe(true)
  expect(isPromotion(fen, 'a1', 'a8')).toBe(false) // a rook
  expect(isPromotion('8/P6k/8/8/8/8/1p5K/R7 b - - 0 1', 'b2', 'b1')).toBe(true)
})
