import type { CoachEvent, EnginePositionRequest } from '../api/sse'
import type { EngineResult } from '../api/types'
import { fakeApi } from '../test/fakes'
import { type ChatProgress, askCoach } from './chat'

type Emit = (event: CoachEvent) => void

const POSITIONS: EnginePositionRequest[] = [
  { fen: 'fen-a w', label: 'position' },
  { fen: 'fen-b b', label: 'after_candidate' },
]

function deepResult(fen: string): EngineResult {
  return { ply: null, fen, tier: 'deep', depth: 22, time_ms: 3000, lines: [] }
}

test('a plain question returns the coach text', async () => {
  const progress: ChatProgress[] = []
  const deps = { api: fakeApi(), analyzeDeep: vi.fn() }

  const reply = await askCoach(deps, 'g1', 'Why did I lose?', (p) => progress.push(p))

  expect(reply).toBe('Good question.')
  expect(deps.api.sendChat).toHaveBeenCalledWith('g1', 'Why did I lose?', expect.any(Function))
  expect(deps.analyzeDeep).not.toHaveBeenCalled()
  expect(progress).toEqual(['writing'])
})

test('an engine request runs the deep dive and sends the results back', async () => {
  const progress: ChatProgress[] = []
  const api = fakeApi({
    sendChat: vi.fn(async (_g: string, _m: string, emit: Emit) => {
      emit({ type: 'status', message: 'Coach is writing…' })
      emit({ type: 'engine_request', request_id: 'r1', positions: POSITIONS })
    }),
    submitEngineResult: vi.fn(async (_g: string, _r: string, _res: EngineResult[], emit: Emit) => {
      emit({ type: 'text', text: 'With 14. Nxe5 you win a pawn.' })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  const analyzeDeep = vi.fn(async (positions: EnginePositionRequest[]) =>
    positions.map((p) => deepResult(p.fen)),
  )

  const reply = await askCoach({ api, analyzeDeep }, 'g1', 'What if Nxe5?', (p) => progress.push(p))

  expect(reply).toBe('With 14. Nxe5 you win a pawn.')
  expect(analyzeDeep).toHaveBeenCalledWith(POSITIONS)
  expect(api.submitEngineResult).toHaveBeenCalledWith(
    'g1',
    'r1',
    [deepResult('fen-a w'), deepResult('fen-b b')],
    expect.any(Function),
  )
  expect(progress).toEqual(['writing', 'thinking', 'writing'])
})

test('a coach error is thrown with its message', async () => {
  const api = fakeApi({
    sendChat: vi.fn(async (_g: string, _m: string, emit: Emit) => {
      emit({ type: 'error', message: 'The coach is unavailable right now.' })
    }),
  })

  await expect(askCoach({ api, analyzeDeep: vi.fn() }, 'g1', 'Hi', () => {})).rejects.toThrow(
    'The coach is unavailable right now.',
  )
})

test('a stream that ends without an answer is a lost connection', async () => {
  const api = fakeApi({ sendChat: vi.fn(async () => {}) })

  await expect(askCoach({ api, analyzeDeep: vi.fn() }, 'g1', 'Hi', () => {})).rejects.toThrow(
    'The connection to the coach was lost.',
  )
})
