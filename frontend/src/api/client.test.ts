import { ApiError, createApiClient } from './client'

function respond(status: number, body: unknown) {
  return vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

const request = { pgn: '1. e4 *', user_color: 'white' as const, elo: 1200, playstyle: null }

test('posts JSON and returns the parsed body', async () => {
  const fetchImpl = respond(201, { game_id: 'g1', positions: [], final_fen: 'x', final_is_terminal: false })

  const game = await createApiClient(fetchImpl).createGame(request)

  expect(game.game_id).toBe('g1')
  const [url, init] = fetchImpl.mock.calls[0]
  expect(url).toBe('/api/games')
  expect(init?.method).toBe('POST')
  expect(JSON.parse(String(init?.body))).toEqual(request)
})

test('sends engine results to the game-specific endpoints', async () => {
  const fetchImpl = respond(200, { verify_fens: [] })

  await createApiClient(fetchImpl).submitScan('g1', [])

  expect(fetchImpl.mock.calls[0][0]).toBe('/api/games/g1/engine/scan')
})

test.each([
  ['a PGN error message', { detail: { code: 'illegal_move', message: 'Move 2 (White): Ke3 is not a legal move in that position.', move_number: 2 } }, 'Move 2 (White): Ke3 is not a legal move in that position.'],
  ['a plain detail string', { detail: 'Game not found.' }, 'Game not found.'],
  ['a validation error list', { detail: [{ msg: 'Input should be greater than or equal to 100' }] }, 'Input should be greater than or equal to 100'],
  ['an unknown body', { oops: true }, 'Something went wrong (error 422). Please try again.'],
])('turns %s into a readable ApiError', async (_, body, message) => {
  const failure = createApiClient(respond(422, body)).createGame(request)

  await expect(failure).rejects.toEqual(new ApiError(422, message))
})

test('reports an unreachable server', async () => {
  const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'))

  await expect(createApiClient(fetchImpl).engineConfig()).rejects.toThrow("Couldn't reach the CoChess server")
})

test('streams synopsis events from the SSE response', async () => {
  const sse = 'event: status\ndata: {"message": "Coach is writing…"}\n\nevent: done\ndata: {"invalid_moves_removed": []}\n\n'
  const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(sse, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
  )
  const events: unknown[] = []

  await createApiClient(fetchImpl).streamSynopsis('g1', (event) => events.push(event))

  expect(fetchImpl.mock.calls[0][0]).toBe('/api/games/g1/synopsis')
  expect(events).toEqual([
    { type: 'status', message: 'Coach is writing…' },
    { type: 'done', invalid_moves_removed: [] },
  ])
})

test('a synopsis the server refuses becomes an ApiError', async () => {
  const fetchImpl = respond(503, { detail: "The coach isn't set up on this server yet." })

  await expect(createApiClient(fetchImpl).streamSynopsis('g1', () => {})).rejects.toEqual(
    new ApiError(503, "The coach isn't set up on this server yet."),
  )
})
