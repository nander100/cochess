import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from './App'
import type { PipelineDeps } from './analysis/pipeline'
import { ApiError } from './api/client'
import type { CoachEvent } from './api/sse'
import { PROFILE, fakeDeps } from './test/fakes'

function renderApp(deps: PipelineDeps, path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App deps={deps} />
    </MemoryRouter>,
  )
}

async function submitGame() {
  fireEvent.change(await screen.findByLabelText(/your game/i), {
    target: { value: '1. e4 e5 2. Nf3 *' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
}

test('renders the app title', async () => {
  renderApp(fakeDeps())

  expect(await screen.findByRole('heading', { name: 'CoChess' })).toBeInTheDocument()
})

test('runs the analysis and shows engine details when done', async () => {
  renderApp(fakeDeps())

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
  renderApp(deps)

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
  renderApp(deps)

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
  renderApp(deps)

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
  renderApp(deps)

  await submitGame()

  expect(await screen.findByText('The coach is unavailable right now.')).toBeInTheDocument()
})

test('no synopsis is requested before the summary is ready', async () => {
  const deps = fakeDeps()
  renderApp(deps)

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
  renderApp(deps)
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
  renderApp(deps)
  await submitGame()

  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('Second time lucky.')).toBeInTheDocument()
})

const LOGGED_OUT = new ApiError(401, "You're not logged in. Ask the owner for a new login link.")

test('without a session the app asks for a login link', async () => {
  renderApp(fakeDeps({ me: vi.fn().mockRejectedValue(LOGGED_OUT) }))

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
  expect(screen.queryByLabelText(/your game/i)).not.toBeInTheDocument()
})

test('a 401 in the middle of a session shows the logged-out message', async () => {
  renderApp(fakeDeps({ createGame: vi.fn().mockRejectedValue(LOGGED_OUT) }))

  await submitGame()

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
})

test('the header shows who is logged in, and logging out ends the session', async () => {
  const deps = fakeDeps()
  renderApp(deps)

  expect(await screen.findByText('Alex')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Log out' }))

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
  expect(deps.api.logout).toHaveBeenCalled()
})

test('a login link redeems the token, then opens the app', async () => {
  const deps = fakeDeps()
  renderApp(deps, '/redeem#token=abc123')

  expect(await screen.findByLabelText(/your game/i)).toBeInTheDocument()
  expect(deps.api.redeem).toHaveBeenCalledTimes(1)
  expect(deps.api.redeem).toHaveBeenCalledWith('abc123')
})

test('a used login link shows why it failed', async () => {
  const used = new ApiError(400, 'This login link has expired or was already used.')
  renderApp(fakeDeps({ redeem: vi.fn().mockRejectedValue(used) }), '/redeem#token=abc123')

  expect(await screen.findByRole('alert')).toHaveTextContent('expired or was already used')
})

test('a new player fills in the profile first, then can analyze', async () => {
  const blank = { ...PROFILE, elo: null, time_control: null, complete: false }
  const deps = fakeDeps({ me: vi.fn(async () => blank) })
  renderApp(deps)

  fireEvent.change(await screen.findByLabelText(/rating/i), { target: { value: '1450' } })
  fireEvent.change(screen.getByLabelText(/time control/i), { target: { value: 'blitz' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

  expect(await screen.findByLabelText(/your game/i)).toBeInTheDocument()
  expect(deps.api.updateMe).toHaveBeenCalledWith({
    name: 'Alex',
    elo: 1450,
    time_control: 'blitz',
    playstyle: '',
  })
})
