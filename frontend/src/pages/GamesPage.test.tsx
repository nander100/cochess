import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { Dashboard, GameListItem } from '../api/types'
import { ApiError } from '../api/client'
import { EMPTY_DASHBOARD, EMPTY_TENDENCIES, fakeDeps } from '../test/fakes'
import { ToastProvider } from '../ui'
import { GamesPage } from './GamesPage'

function game(id: string, overrides: Partial<GameListItem> = {}): GameListItem {
  return {
    id,
    played_at: '2026-10-01T18:04:05Z',
    opponent: `Rival ${id}`,
    user_color: 'white',
    user_result: 'win',
    time_control: '600',
    opening: null,
    accuracy: 80,
    status: 'analyzed',
    time_control_category: 'rapid',
    moments_total: 3,
    moments_done: 1,
    ...overrides,
  }
}

const TENDENCIES = {
  ...EMPTY_TENDENCIES,
  games_analyzed: 6,
  tendencies: [
    { theme: 'hung_piece', label: 'Leaving pieces undefended', rate_per_game: 1, score: 2, trend: null, games_seen: 4,
      provisional: false, recent_example: { game_id: 'a', move_number: 9, move_san: 'Nf3' } },
    { theme: 'missed_tactic', label: 'Missing tactics', rate_per_game: 0.5, score: 1, trend: null, games_seen: 2,
      provisional: false, recent_example: { game_id: 'b', move_number: 15, move_san: 'Qd2' } },
  ],
}  // prettier-ignore

function renderPage(games: GameListItem[], tendencies = TENDENCIES, dashboard: Dashboard = EMPTY_DASHBOARD) {
  const deps = fakeDeps({
    listGames: vi.fn(async () => games),
    tendencies: vi.fn(async () => tendencies),
    dashboard: vi.fn(async () => dashboard),
  })
  render(
    <MemoryRouter>
      <ToastProvider>
        <GamesPage deps={deps} onLoggedOut={vi.fn()} />
      </ToastProvider>
    </MemoryRouter>,
  )
  return deps
}

async function upload(deps: ReturnType<typeof fakeDeps>, error: Error) {
  vi.mocked(deps.api.createGame).mockRejectedValue(error)
  fireEvent.click(screen.getByLabelText('I played White'))
  fireEvent.change(screen.getByLabelText(/your game/i), { target: { value: '1. e4 e5 *' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze game' }))
  return screen.findByRole('alert')
}

test('the upload form sits in the hero, with the color first', async () => {
  renderPage([])

  expect(screen.getByRole('heading', { level: 1, name: 'Upload a game. Learn one idea from it.' })).toBeInTheDocument()
  expect(screen.getByLabelText('I played White')).not.toBeChecked()
  expect(await screen.findByRole('heading', { name: 'No games yet' })).toBeInTheDocument()
})

const DASHBOARD: Dashboard = {
  ...EMPTY_DASHBOARD,
  games: 2,
  focus_areas: [
    {
      theme: 'hung_piece', label: 'Leaving pieces undefended', trend: 'improving', rate_per_game: 1.2,
      games_seen: 4, example_game_id: 'a', example_move: '9. Nf3', example_ply: 17,
      puzzles: [{ theme: 'hangingPiece', label: 'Hanging piece', url: 'https://lichess.org/training/hangingPiece' }],
    },
  ],
  continue_games: [{ game_id: 'a', opponent: 'Rival a', played_at: '2026-10-01T18:04:05Z', moments_total: 3, moments_done: 1 }],
  recent: [
    { game_id: 'a', played_at: '2026-10-01T18:04:05Z', opponent: 'Rival a', color: 'white', result: 'win',
      accuracy: 80, moments_total: 3, moments_done: 1 },
  ],
  onboarding: { complete: false, analyzed: 5, total: 12, has_report: false },
} // prettier-ignore

test('the dashboard shows focus areas, games to continue, recent games and the assessment', async () => {
  const deps = renderPage([game('a')], TENDENCIES, DASHBOARD)

  const focus = await screen.findByRole('article', { name: 'Leaving pieces undefended' })
  expect(within(focus).getByText('↓ Improving')).toBeInTheDocument()
  expect(within(focus).getByRole('link', { name: /See an example \(9\. Nf3\)/ })).toHaveAttribute('href', '/games/a?ply=17')
  expect(within(focus).getByRole('link', { name: 'Hanging piece' })).toHaveAttribute(
    'href', 'https://lichess.org/training/hangingPiece',
  ) // prettier-ignore
  const resume = screen.getByRole('region', { name: 'Continue where you left off' })
  expect(within(resume).getByRole('link', { name: /vs Rival a/ })).toHaveAttribute('href', '/games/a?view=moments')
  expect(within(screen.getByRole('table', { name: 'Recent analyzed games' })).getByText('1/3')).toBeInTheDocument()
  expect(screen.getByText(/5 of 12 games analyzed/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Continue the assessment →' })).toHaveAttribute('href', '/onboarding')
  expect(deps.api.dashboard).toHaveBeenCalledWith({ tc: null, color: null, range: 'all' })
})

test('the dashboard filters ask again with the time control, color and range', async () => {
  const deps = renderPage([game('a')], TENDENCIES, DASHBOARD)
  await screen.findByRole('article', { name: 'Leaving pieces undefended' })

  fireEvent.change(screen.getByLabelText('Time control'), { target: { value: 'blitz' } })
  fireEvent.change(screen.getByLabelText('Color'), { target: { value: 'black' } })
  fireEvent.change(screen.getByLabelText('Range'), { target: { value: '10' } })

  await vi.waitFor(() =>
    expect(deps.api.dashboard).toHaveBeenLastCalledWith({ tc: 'blitz', color: 'black', range: '10' }),
  )
})

test('a new player is told how to get started', async () => {
  renderPage([])

  expect(await screen.findByRole('heading', { name: 'Nothing to show yet' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'start your 12-game assessment' })).toHaveAttribute('href', '/onboarding')
})

test('all games filter by time control', async () => {
  renderPage([game('a'), game('b', { time_control_category: 'blitz', opponent: 'Blitz rival' })])
  const table = await screen.findByRole('table', { name: 'All games' })
  expect(within(table).getAllByRole('row')).toHaveLength(3)

  fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'blitz' } })

  expect(within(screen.getByRole('table', { name: 'All games' })).getByText('Blitz rival')).toBeInTheDocument()
  expect(screen.queryByText('Rival a')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'classical' } })
  expect(screen.getByRole('heading', { name: 'No games in this time control' })).toBeInTheDocument()
})

test('each row shows the color with a swatch and the status as a pill', async () => {
  renderPage([game('a', { user_color: 'black', status: 'scanned', accuracy: null })])

  const row = (await screen.findAllByRole('row'))[1]
  expect(within(row).getByText('Black')).toBeInTheDocument()
  expect(within(row).getByText('Analyzing…')).toHaveClass('ui-pill-busy')
  expect(within(row).getByRole('link', { name: 'Open the game vs Rival a' })).toHaveAttribute('href', '/games/a')
})

test('a problem with the pasted game is shown by the form', async () => {
  const deps = renderPage([])

  const alert = await upload(deps, new ApiError(422, 'Move 2 (White): Ke3 is not a legal move.'))

  expect(alert).toHaveClass('form-error')
  expect(alert).toHaveTextContent('Ke3 is not a legal move')
})

test('a server or connection failure is shown as a toast', async () => {
  const deps = renderPage([])

  const alert = await upload(deps, new ApiError(0, "Couldn't reach the CoChess server. Check your connection and try again."))

  expect(alert.closest('.ui-toast')).not.toBeNull()
  expect(alert).toHaveTextContent("Couldn't reach the CoChess server")
})
