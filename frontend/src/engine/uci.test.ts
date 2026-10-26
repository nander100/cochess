import { parseInfoLine } from './uci'

test('parses depth, multipv, centipawn score and principal variation', () => {
  const line =
    'info depth 18 seldepth 24 multipv 2 score cp -35 nodes 812345 nps 1200000 hashfull 120 tbhits 0 time 677 pv e7e5 g1f3 b8c6'

  expect(parseInfoLine(line)).toEqual({
    depth: 18,
    multipv: 2,
    score: { kind: 'cp', value: -35 },
    pv: ['e7e5', 'g1f3', 'b8c6'],
  })
})

test('parses mate scores and defaults multipv to 1', () => {
  expect(parseInfoLine('info depth 30 score mate -3 time 5 pv h7h8 g8h8 d1h5')).toEqual({
    depth: 30,
    multipv: 1,
    score: { kind: 'mate', value: -3 },
    pv: ['h7h8', 'g8h8', 'd1h5'],
  })
})

test.each([
  ['aspiration bound', 'info depth 20 multipv 1 score cp 40 lowerbound nodes 1 time 1 pv e2e4'],
  ['upper bound', 'info depth 20 multipv 1 score cp 40 upperbound nodes 1 time 1 pv e2e4'],
  ['currmove update', 'info depth 20 currmove e2e4 currmovenumber 1'],
  ['info string', 'info string NNUE evaluation using nn-small.nnue'],
  ['no pv', 'info depth 1 score cp 10 nodes 20 time 1'],
  ['bestmove', 'bestmove e2e4 ponder e7e5'],
  ['uciok', 'uciok'],
])('ignores %s', (_, line) => {
  expect(parseInfoLine(line)).toBeNull()
})
