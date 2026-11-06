import type { CoachEvent, EnginePositionRequest } from '../api/sse'
import type { EngineResult } from '../api/types'
import { fakeApi } from '../test/fakes'
import { type ChatProgress, askCoach, explainPosition } from './chat'

type Emit = (event: CoachEvent) => void

const POSITIONS: EnginePositionRequest[] = [
  { fen: 'fen-a w', label: 'position' },
  { fen: 'fen-b b', label: 'after_candidate' },
]

const ASK = { message: 'Why did I lose?', path_uci: ['e2e4'] }

function deepResult(fen: string): EngineResult {
  return { ply: null, fen, tier: 'deep', depth: 22, time_ms: 3000, lines: [] }
}

test('a plain question returns the coach text', async () => {
  const progress: ChatProgress[] = []
  const deps = { api: fakeApi(), analyzeDeep: vi.fn() }

  const reply = await askCoach(deps, 'g1', ASK, (p) => progress.push(p))

  expect(reply).toEqual({ text: 'Good question.', annotations: [] })
  expect(deps.api.sendChat).toHaveBeenCalledWith('g1', ASK, expect.any(Function))
  expect(deps.analyzeDeep).not.toHaveBeenCalled()
  expect(progress).toEqual(['writing'])
})

test('an engine request runs the deep dive and sends the results back', async () => {
  const progress: ChatProgress[] = []
  const api = fakeApi({
    sendChat: vi.fn(async (_g: string, _m: unknown, emit: Emit) => {
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

  const reply = await askCoach({ api, analyzeDeep }, 'g1', ASK, (p) => progress.push(p))

  expect(reply).toEqual({ text: 'With 14. Nxe5 you win a pawn.', annotations: [] })
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
    sendChat: vi.fn(async (_g: string, _m: unknown, emit: Emit) => {
      emit({ type: 'error', message: 'The coach is unavailable right now.' })
    }),
  })

  await expect(askCoach({ api, analyzeDeep: vi.fn() }, 'g1', ASK, () => {})).rejects.toThrow(
    'The coach is unavailable right now.',
  )
})

test('a stream that ends without an answer is a lost connection', async () => {
  const api = fakeApi({ sendChat: vi.fn(async () => {}) })

  await expect(askCoach({ api, analyzeDeep: vi.fn() }, 'g1', ASK, () => {})).rejects.toThrow(
    'The connection to the coach was lost.',
  )
})

test('explain sends the board position and returns the coach text', async () => {
  const deps = { api: fakeApi(), analyzeDeep: vi.fn() }
  const position = { path_uci: ['e2e4', 'e7e5'] }

  const reply = await explainPosition(deps, 'g1', position, () => {})

  expect(reply).toEqual({ text: 'Here is the position.', annotations: [] })
  expect(deps.api.explain).toHaveBeenCalledWith('g1', position, expect.any(Function))
})

test('board tags arrive as annotation events and come back with the text', async () => {
  const annotation = {
    tag_index: 0,
    char_offset: 4,
    arrows: [{ orig: 'e2', dest: 'e4', color: 'green' as const }],
    squares: [],
  }
  const api = fakeApi({
    sendChat: vi.fn(async (_id: string, _request: unknown, emit: Emit) => {
      emit({ type: 'text', text: 'See [board](cc:board/0).' })
      emit({ type: 'annotation', annotation })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })

  const reply = await askCoach({ api, analyzeDeep: vi.fn() }, 'g1', ASK, () => {})

  expect(reply).toEqual({ text: 'See [board](cc:board/0).', annotations: [annotation] })
})
