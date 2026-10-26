import type { TierConfig } from '../api/types'
import { FakeTransport, info } from '../test/fakeTransport'
import { STOP_GRACE_MS, search, toEngineResult } from './search'

const FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
const SCAN: TierConfig = { multipv: 1, min_time_ms: 250, min_depth: 12, hard_cap_ms: 1000, max_line_plies: 1 }
const VERIFY: TierConfig = { multipv: 4, min_time_ms: 1500, min_depth: 18, hard_cap_ms: 3000, max_line_plies: 10 }

let engine: FakeTransport

beforeEach(() => {
  vi.useFakeTimers()
  engine = new FakeTransport()
  // A real engine answers `stop` with its final line and `bestmove`.
  engine.respond = (command, transport) => {
    if (command === 'stop') transport.emit('bestmove e7e5 ponder g1f3')
  }
})

afterEach(() => {
  vi.useRealTimers()
})

function start(tier: TierConfig) {
  return search(engine, FEN, tier, { now: () => Date.now() })
}

test('sets up the position and searches without a limit', () => {
  void start(VERIFY)

  expect(engine.sent).toEqual([
    'setoption name MultiPV value 4',
    `position fen ${FEN}`,
    'go infinite',
  ])
})

test('fast machine: reaches min depth early and stops at the minimum time', async () => {
  const result = start(SCAN)
  engine.emit(info(20, 'cp 30', 'e7e5'))

  await vi.advanceTimersByTimeAsync(249)
  expect(engine.sent).not.toContain('stop')
  await vi.advanceTimersByTimeAsync(1)

  expect(engine.sent).toContain('stop')
  await expect(result).resolves.toMatchObject({ depth: 20, timeMs: 250 })
})

test('min depth gate: past the minimum time it waits for the minimum depth', async () => {
  const result = start(SCAN)
  engine.emit(info(10, 'cp 30', 'e7e5'))
  await vi.advanceTimersByTimeAsync(400)
  expect(engine.sent).not.toContain('stop')

  engine.emit(info(12, 'cp 25', 'c7c5'))

  expect(engine.sent).toContain('stop')
  await expect(result).resolves.toMatchObject({ depth: 12, timeMs: 400 })
})

test('slow machine: stops at the hard cap even below the minimum depth', async () => {
  const result = start(SCAN)
  engine.emit(info(8, 'cp 30', 'e7e5'))

  await vi.advanceTimersByTimeAsync(999)
  expect(engine.sent).not.toContain('stop')
  await vi.advanceTimersByTimeAsync(1)

  await expect(result).resolves.toMatchObject({ depth: 8, timeMs: 1000 })
})

test('collects the latest line for each multipv, ordered, ignoring bounds and extras', async () => {
  const result = start({ ...VERIFY, multipv: 2, min_time_ms: 0, min_depth: 99 })
  engine.emit(info(5, 'cp 10', 'd7d5', 2))
  engine.emit(info(5, 'cp 40', 'e7e5'))
  engine.emit(info(6, 'cp 45', 'e7e5 g1f3'))
  engine.emit('info depth 7 multipv 1 score cp 90 lowerbound nodes 1 time 1 pv e7e5')
  engine.emit(info(6, 'cp 5', 'a7a6', 3)) // beyond the requested MultiPV

  await vi.advanceTimersByTimeAsync(VERIFY.hard_cap_ms)

  const outcome = await result
  expect(outcome.depth).toBe(6)
  expect(outcome.lines.map((line) => [line.multipv, line.score.value, line.pv])).toEqual([
    [1, 45, ['e7e5', 'g1f3']],
    [2, 10, ['d7d5']],
  ])
})

test('stops listening once the search is over', async () => {
  const result = start(SCAN)
  engine.emit(info(15, 'cp 30', 'e7e5'))
  await vi.advanceTimersByTimeAsync(250)
  await result

  expect(engine.listenerCount).toBe(0)
})

test('fails if the engine never answers stop', async () => {
  engine.respond = () => {}
  const result = start(SCAN)
  const failed = expect(result).rejects.toThrow('The engine stopped responding.')

  await vi.advanceTimersByTimeAsync(SCAN.hard_cap_ms + STOP_GRACE_MS)

  await failed
})

test('converts an outcome into a White-POV result with lines truncated to the tier', () => {
  const outcome = {
    depth: 19,
    timeMs: 1620,
    lines: [
      { depth: 19, multipv: 1, score: { kind: 'cp' as const, value: 35 }, pv: Array(12).fill('e7e5') },
      { depth: 19, multipv: 2, score: { kind: 'mate' as const, value: -2 }, pv: ['d7d5'] },
    ],
  }

  const result = toEngineResult(FEN, 2, 'verify', VERIFY, outcome)

  expect(result).toMatchObject({ ply: 2, fen: FEN, tier: 'verify', depth: 19, time_ms: 1620 })
  expect(result.lines[0]).toMatchObject({ rank: 1, eval_cp: -35, mate: null })
  expect(result.lines[0].moves_uci).toHaveLength(10)
  expect(result.lines[1]).toEqual({ rank: 2, eval_cp: null, mate: 2, moves_uci: ['d7d5'] })
})
