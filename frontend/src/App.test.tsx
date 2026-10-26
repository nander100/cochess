import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import { ApiError } from './api/client'
import type { CoachEvent } from './api/sse'
import { ENGINE_CONFIG, fakeDeps } from './test/fakes'

async function submitGame() {
  fireEvent.change(await screen.findByLabelText(/rating/i), { target: { value: '1350' } })
  fireEvent.change(screen.getByLabelText(/your game/i), { target: { value: '1. e4 e5 2. Nf3 *' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
}

test('renders the app title', async () => {
  render(<App deps={fakeDeps()} />)

  expect(await screen.findByRole('heading', { name: 'CoChess' })).toBeInTheDocument()
})

test('runs the analysis and shows engine details when done', async () => {
  render(<App deps={fakeDeps()} />)

  await submitGame()

  expect(await screen.findByText('Analysis complete.')).toBeInTheDocument()
  expect(screen.getByText(/stockfish-19-lite, 3 thread\(s\)/)).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(1 + 4 + 2) // header + scan + verify
})

test('shows accuracy and error counts from the game summary', async () => {
  const deps = fakeDeps({
    submitVerify: vi.fn(async () => ({
      summary_ready: true,
      counts: { inaccuracies: 1, mistakes: 2, blunders: 0, missed_mates: 0 },
      accuracy: { user: 72, opponent: 53.3 },
    })),
  })
  render(<App deps={deps} />)

  await submitGame()

  const headline = await screen.findByText(/Your accuracy/)
  expect(headline).toHaveTextContent(
    'Your accuracy: 72% (opponent 53.3%) · 1 inaccuracy, 2 mistakes, 0 blunders',
  )
})

test('shows the server error when the PGN is rejected', async () => {
  const deps = fakeDeps({
    createGame: vi.fn(async () => {
      throw new ApiError(422, "Non-standard starting positions aren't supported.")
    }),
  })
  render(<App deps={deps} />)

  await submitGame()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Non-standard starting positions aren't supported.",
  )
  expect(screen.getByRole('button', { name: 'Analyze' })).toBeEnabled()
})

test('the coach writes a synopsis once the summary is ready', async () => {
  const deps = fakeDeps({
    submitVerify: vi.fn(async () => ({
      summary_ready: true,
      counts: { inaccuracies: 0, mistakes: 0, blunders: 0, missed_mates: 0 },
      accuracy: { user: 90, opponent: 80 },
    })),
  })
  render(<App deps={deps} />)

  await submitGame()

  expect(await screen.findByRole('heading', { name: 'Overall' })).toBeInTheDocument()
  expect(screen.getByText('A tidy game.')).toBeInTheDocument()
  expect(deps.api.streamSynopsis).toHaveBeenCalledWith('game-1', expect.any(Function))
})

test('a coach error is shown in the synopsis panel', async () => {
  const deps = fakeDeps({
    submitVerify: vi.fn(async () => ({
      summary_ready: true,
      counts: { inaccuracies: 0, mistakes: 0, blunders: 0, missed_mates: 0 },
      accuracy: { user: 90, opponent: 80 },
    })),
    streamSynopsis: vi.fn(async (_id: string, onEvent: (event: CoachEvent) => void) => {
      onEvent({ type: 'error', message: 'The coach is unavailable right now.' })
    }),
  })
  render(<App deps={deps} />)

  await submitGame()

  expect(await screen.findByText('The coach is unavailable right now.')).toBeInTheDocument()
})

test('no synopsis is requested before the summary is ready', async () => {
  const deps = fakeDeps()
  render(<App deps={deps} />)

  await submitGame()

  await screen.findByText('Analysis complete.')
  expect(deps.api.streamSynopsis).not.toHaveBeenCalled()
})

test('after the synopsis, a what-if question runs the deep tier on the engine', async () => {
  const deps = fakeDeps({
    submitVerify: vi.fn(async () => ({
      summary_ready: true,
      counts: { inaccuracies: 0, mistakes: 0, blunders: 0, missed_mates: 0 },
      accuracy: { user: 90, opponent: 80 },
    })),
    sendChat: vi.fn(async (_g: string, _m: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'engine_request', request_id: 'r1', positions: [{ fen: 'fen-1 b', label: 'position' }] })
    }),
    submitEngineResult: vi.fn(async (_g: string, _r: string, _res: unknown, emit: (event: CoachEvent) => void) => {
      emit({ type: 'text', text: 'The engine likes your idea.' })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  render(<App deps={deps} />)
  await submitGame()
  await screen.findByRole('heading', { name: 'Overall' })

  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'What if e5?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByText('The engine likes your idea.')).toBeInTheDocument()
  expect(deps.engine.analyze).toHaveBeenLastCalledWith(
    { fen: 'fen-1 b', ply: null },
    'deep',
    expect.objectContaining({ multipv: 4 }),
  )
})

const DENIED = new ApiError(401, 'Enter the access code to use CoChess.')

test('a gated server shows the access gate, and the right code opens the app', async () => {
  const engineConfig = vi.fn().mockRejectedValueOnce(DENIED).mockRejectedValueOnce(DENIED)
    .mockResolvedValue(ENGINE_CONFIG)
  render(<App deps={fakeDeps({ engineConfig })} />)

  fireEvent.change(await screen.findByLabelText('Access code'), { target: { value: 'wrong' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(await screen.findByRole('alert')).toHaveTextContent("That access code didn't work.")

  fireEvent.change(screen.getByLabelText('Access code'), { target: { value: 'right' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

  expect(await screen.findByLabelText(/rating/i)).toBeInTheDocument()
  expect(sessionStorage.getItem('cochess-access-code')).toBe('right')
})

test('a 401 in the middle of a session returns to the gate', async () => {
  render(<App deps={fakeDeps({ createGame: vi.fn().mockRejectedValue(DENIED) })} />)

  await submitGame()

  expect(await screen.findByLabelText('Access code')).toBeInTheDocument()
  expect(screen.getByRole('alert')).toHaveTextContent('Please enter the access code again.')
})

test('a failed synopsis can be retried', async () => {
  const streamSynopsis = vi
    .fn()
    .mockImplementationOnce(async (_g: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'error', message: 'The coach is unavailable right now.' })
    })
    .mockImplementationOnce(async (_g: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'text', text: '### Overall\nSecond time lucky.' })
      emit({ type: 'done', invalid_moves_removed: [] })
    })
  const deps = fakeDeps({
    streamSynopsis,
    submitVerify: vi.fn(async () => ({
      summary_ready: true,
      counts: { inaccuracies: 0, mistakes: 0, blunders: 0, missed_mates: 0 },
      accuracy: { user: 90, opponent: 80 },
    })),
  })
  render(<App deps={deps} />)
  await submitGame()

  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('Second time lucky.')).toBeInTheDocument()
})
