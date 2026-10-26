import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import { ApiError } from './api/client'
import type { CoachEvent } from './api/sse'
import { fakeDeps } from './test/fakes'

function submitGame() {
  fireEvent.change(screen.getByLabelText(/rating/i), { target: { value: '1350' } })
  fireEvent.change(screen.getByLabelText(/your game/i), { target: { value: '1. e4 e5 2. Nf3 *' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
}

test('renders the app title', () => {
  render(<App deps={fakeDeps()} />)

  expect(screen.getByRole('heading', { name: 'CoChess' })).toBeInTheDocument()
})

test('runs the analysis and shows engine details when done', async () => {
  render(<App deps={fakeDeps()} />)

  submitGame()

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

  submitGame()

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

  submitGame()

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

  submitGame()

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

  submitGame()

  expect(await screen.findByText('The coach is unavailable right now.')).toBeInTheDocument()
})

test('no synopsis is requested before the summary is ready', async () => {
  const deps = fakeDeps()
  render(<App deps={deps} />)

  submitGame()

  await screen.findByText('Analysis complete.')
  expect(deps.api.streamSynopsis).not.toHaveBeenCalled()
})
