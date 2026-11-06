import { ApiError } from '../api/client'
import type { CoachEvent } from '../api/sse'
import type { EngineResult, WalkthroughRequest } from '../api/types'
import { fakeApi, walkthroughFor } from '../test/fakes'
import { type WalkthroughProgress, positionsAlong, walkThrough } from './walkthrough'

const START = ['e2e4', 'e7e5']
const LINE = ['g1f3', 'b8c6']

function scanOf(fen: string): EngineResult {
  return { ply: null, fen, tier: 'verify', depth: 18, time_ms: 1500, lines: [] }
}

test('a line walked before comes from the cache, with no engine work', async () => {
  const api = fakeApi()
  const scan = vi.fn()

  const walk = await walkThrough({ api, search: scan }, 'g1', START, LINE, () => {})

  expect(walk.steps.map((s) => s.san)).toEqual(['Nf3', 'Nc6'])
  expect(scan).not.toHaveBeenCalled()
  expect(api.walkthrough).toHaveBeenCalledWith(
    'g1',
    { start_path_uci: START, line_uci: LINE, step_results: [] },
    expect.any(Function),
  )
})

test('a new line is scanned position by position, with progress, then sent', async () => {
  let calls = 0
  const api = fakeApi({
    walkthrough: vi.fn(async (_id: string, body: WalkthroughRequest, emit: (e: CoachEvent) => void) => {
      calls += 1
      if (body.step_results.length === 0) throw new ApiError(428, 'Analyze every position first.')
      emit({ type: 'walkthrough', walkthrough: walkthroughFor(body) })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  const scan = vi.fn(async (fen: string) => scanOf(fen))
  const progress: WalkthroughProgress[] = []

  await walkThrough({ api, search: scan }, 'g1', START, LINE, (p) => progress.push(p))

  const fens = positionsAlong(START, LINE)
  expect(scan.mock.calls.map(([fen]) => fen)).toEqual(fens)
  expect(progress).toEqual([
    { kind: 'writing' },
    { kind: 'scanning', done: 0, total: 3 },
    { kind: 'scanning', done: 1, total: 3 },
    { kind: 'scanning', done: 2, total: 3 },
    { kind: 'writing' },
  ])
  expect(calls).toBe(2)
  expect(vi.mocked(api.walkthrough).mock.calls[1][1].step_results.map((r) => r.fen)).toEqual(fens)
})

test('checkmate and stalemate positions are not scanned', async () => {
  const api = fakeApi({
    walkthrough: vi.fn(async (_id: string, body: WalkthroughRequest, emit: (e: CoachEvent) => void) => {
      if (body.step_results.length === 0) throw new ApiError(428, 'scan first')
      emit({ type: 'walkthrough', walkthrough: walkthroughFor(body) })
    }),
  })
  const scan = vi.fn(async (fen: string) => scanOf(fen))
  // Fool's mate: 1. f3 e5 2. g4 Qh4#.
  await walkThrough({ api, search: scan }, 'g1', ['f2f3', 'e7e5', 'g2g4'], ['d8h4'], () => {})

  expect(scan).toHaveBeenCalledTimes(1)
})

test('a coach error or any other refusal is thrown as a readable message', async () => {
  const failing = fakeApi({
    walkthrough: vi.fn(async (_id: string, _body: WalkthroughRequest, emit: (e: CoachEvent) => void) => {
      emit({ type: 'error', message: "The coach couldn't put this walkthrough together. Please try again." })
    }),
  })
  await expect(walkThrough({ api: failing, search: vi.fn() }, 'g1', START, LINE, () => {})).rejects.toThrow(
    "couldn't put this walkthrough together",
  )

  const withheld = fakeApi({ walkthrough: vi.fn(async () => { throw new ApiError(409, 'Solve or reveal this critical moment first.') }) })
  await expect(walkThrough({ api: withheld, search: vi.fn() }, 'g1', START, LINE, () => {})).rejects.toThrow('Solve or reveal')

  const silent = fakeApi({ walkthrough: vi.fn(async () => {}) })
  await expect(walkThrough({ api: silent, search: vi.fn() }, 'g1', START, LINE, () => {})).rejects.toThrow('connection')
})
