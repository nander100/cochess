import type { EngineResult, TierConfig } from '../api/types'
import { analyzeParallel, poolSize } from './pool'
import type { AnalysisItem, Analyzer } from './StockfishEngine'

const TIER: TierConfig = { multipv: 1, min_time_ms: 0, min_depth: 12, hard_cap_ms: 1000, max_line_plies: 1 }
const ITEMS: AnalysisItem[] = Array.from({ length: 12 }, (_, i) => ({ fen: `fen-${i} w`, ply: i + 1 }))

/** A fake engine that records what it searched and can fail on one position. */
function worker(name: string, failOn: string | null = null, delayMs = 0) {
  const searched: string[] = []
  const analyzer: Analyzer = {
    analyze: async (item, tier) => {
      await new Promise((resolve) => setTimeout(resolve, delayMs))
      if (item.fen === failOn) throw new Error(`${name} stopped responding`)
      searched.push(item.fen)
      return { fen: item.fen, ply: item.ply, tier, depth: 12, time_ms: 1, lines: [] } as EngineResult
    },
  }
  return { analyzer, searched }
}

test('every position is searched once and results come back in game order', async () => {
  const workers = [worker('a'), worker('b'), worker('c')]

  const results = await analyzeParallel(workers.map((w) => w.analyzer), ITEMS, 'scan', TIER)

  expect(results.map((r) => r.ply)).toEqual(ITEMS.map((i) => i.ply))
  const all = workers.flatMap((w) => w.searched)
  expect([...all].sort()).toEqual(ITEMS.map((i) => i.fen).sort())
  expect(workers.every((w) => w.searched.length > 0)).toBe(true)
})

test('each worker searches a run of consecutive positions from the end backwards', async () => {
  const solo = worker('a')

  await analyzeParallel([solo.analyzer], ITEMS.slice(0, 4), 'scan', TIER)

  // One worker, chunks of two positions: each chunk backwards, chunks in order.
  expect(solo.searched).toEqual(['fen-1 w', 'fen-0 w', 'fen-3 w', 'fen-2 w'])
})

test('a worker that fails hands its positions to the others', async () => {
  const broken = worker('broken', 'fen-5 w')
  const healthy = worker('healthy', null, 1)

  const results = await analyzeParallel([broken.analyzer, healthy.analyzer], ITEMS, 'scan', TIER)

  expect(results.map((r) => r.fen)).toEqual(ITEMS.map((i) => i.fen))
  expect(healthy.searched).toContain('fen-5 w')
})

test('when every worker fails the analysis fails', async () => {
  const a = worker('a', 'fen-0 w')
  const b = worker('b', 'fen-0 w')

  await expect(analyzeParallel([a.analyzer, b.analyzer], ITEMS.slice(0, 2), 'scan', TIER)).rejects.toThrow(
    'stopped responding',
  )
})

test('progress counts every finished position and ends with the total', async () => {
  const progress: Array<[number, number]> = []

  await analyzeParallel([worker('a').analyzer, worker('b').analyzer], ITEMS, 'scan', TIER, (done, total) =>
    progress.push([done, total]),
  )

  expect(progress[0]).toEqual([0, ITEMS.length])
  expect(progress.at(-1)).toEqual([ITEMS.length, ITEMS.length])
  expect(progress.map(([done]) => done)).toEqual([...progress.map(([done]) => done)].sort((x, y) => x - y))
})

test('no positions, no searches', async () => {
  const a = worker('a')

  expect(await analyzeParallel([a.analyzer], [], 'scan', TIER)).toEqual([])
  expect(a.searched).toEqual([])
})

test('the pool leaves a core for the page and never exceeds the setting', () => {
  expect(poolSize(4, 16)).toBe(4)
  expect(poolSize(4, 3)).toBe(2)
  expect(poolSize(4, 1)).toBe(1)
  expect(poolSize(0, 8)).toBe(1)
})
