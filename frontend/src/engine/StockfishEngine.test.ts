import type { TierConfig } from '../api/types'
import { FakeTransport, info } from '../test/fakeTransport'
import { StockfishEngine, chooseBuild, threadCount, waitForLine } from './StockfishEngine'

const QUICK: TierConfig = { multipv: 1, min_time_ms: 0, min_depth: 1, hard_cap_ms: 100, max_line_plies: 1 }
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'

/** Answers the handshake, and every search with one line at depth 1. */
function workingEngine(): FakeTransport {
  const engine = new FakeTransport()
  engine.respond = (command, transport) => {
    if (command === 'uci') transport.emit('uciok')
    if (command === 'isready') transport.emit('readyok')
    if (command === 'go infinite') transport.emit(info(1, 'cp 20', 'e2e4'))
    if (command === 'stop') transport.emit('bestmove e2e4')
  }
  return engine
}

test('uses the multi-threaded build only when the page is cross-origin isolated', () => {
  expect(chooseBuild(true)).toBe('stockfish-19-lite')
  expect(chooseBuild(false)).toBe('stockfish-19-lite-single')
})

test.each([
  ['stockfish-19-lite', 8, 4, 4],
  ['stockfish-19-lite', 3, 4, 2],
  ['stockfish-19-lite', 1, 4, 1],
  ['stockfish-19-lite-single', 16, 4, 1],
] as const)('%s with %i cores and max %i uses %i thread(s)', (build, cores, max, expected) => {
  expect(threadCount(build, cores, max)).toBe(expected)
})

test('handshake sets threads and hash on the multi-threaded build', async () => {
  const engine = workingEngine()

  await StockfishEngine.connect(engine, 'stockfish-19-lite', 3, 64)

  expect(engine.sent).toEqual([
    'uci',
    'setoption name Threads value 3',
    'setoption name Hash value 64',
    'isready',
  ])
})

test('single-threaded build skips the Threads option', async () => {
  const engine = workingEngine()

  await StockfishEngine.connect(engine, 'stockfish-19-lite-single', 1, 64)

  expect(engine.sent).not.toContain('setoption name Threads value 1')
})

test('runs searches one after another, never overlapping', async () => {
  const engine = workingEngine()
  const stockfish = await StockfishEngine.connect(engine, 'stockfish-19-lite-single', 1, 16)
  engine.sent.length = 0

  const results = await Promise.all([
    stockfish.analyze({ fen: START, ply: 1 }, 'scan', QUICK),
    stockfish.analyze({ fen: AFTER_E4, ply: 2 }, 'scan', QUICK),
  ])

  const searchCommands = engine.sent.filter((c) => c.startsWith('position') || c === 'stop')
  expect(searchCommands).toEqual([`position fen ${START}`, 'stop', `position fen ${AFTER_E4}`, 'stop'])
  expect(results.map((r) => [r.ply, r.lines[0].eval_cp])).toEqual([
    [1, 20],
    [2, -20],
  ])
})

test('newGame clears the hash and waits until the engine is ready', async () => {
  const engine = workingEngine()
  const stockfish = await StockfishEngine.connect(engine, 'stockfish-19-lite-single', 1, 16)

  await stockfish.newGame()

  expect(engine.sent.slice(-2)).toEqual(['ucinewgame', 'isready'])
})

test('waitForLine times out with a readable error', async () => {
  vi.useFakeTimers()
  const pending = waitForLine(new FakeTransport(), 'uciok', 1000)
  const failed = expect(pending).rejects.toThrow(`The chess engine didn't answer (waiting for "uciok").`)

  await vi.advanceTimersByTimeAsync(1000)

  await failed
  vi.useRealTimers()
})
