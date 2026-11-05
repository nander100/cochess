import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { GameListItem } from '../api/types'
import { EMPTY_TENDENCIES, fakeDeps } from '../test/fakes'
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

function renderPage(games: GameListItem[], tendencies = TENDENCIES) {
  const deps = fakeDeps({ listGames: vi.fn(async () => games), tendencies: vi.fn(async () => tendencies) })
  render(
    <MemoryRouter>
      <GamesPage deps={deps} onLoggedOut={vi.fn()} />
    </MemoryRouter>,
  )
  return deps
}

test('the upload form sits in the hero, with the color first', async () => {
  renderPage([])

  expect(screen.getByRole('heading', { level: 1, name: 'Upload a game. Learn one idea from it.' })).toBeInTheDocument()
  expect(screen.getByLabelText('I played White')).not.toBeChecked()
  expect(await screen.findByRole('heading', { name: 'No games yet' })).toBeInTheDocument()
})

test('what keeps coming up: the top two tendencies and moments waiting', async () => {
  renderPage([game('a'), game('b', { moments_total: 2, moments_done: 2 })])

  const section = await screen.findByRole('region', { name: 'What keeps coming up' })
  expect(within(section).getByText('Leaving pieces undefended')).toBeInTheDocument()
  expect(within(section).getByText('Seen in 4 of your last 6 games')).toBeInTheDocument()
  expect(within(section).getByText('Missing tactics')).toBeInTheDocument()
  expect(within(section).getByText('2 waiting')).toBeInTheDocument()
  expect(within(section).getByRole('link', { name: 'Start practicing →' })).toHaveAttribute('href', '/moments')
})

test('recent games filter by time control', async () => {
  renderPage([game('a'), game('b', { time_control_category: 'blitz', opponent: 'Blitz rival' })])
  const table = await screen.findByRole('table', { name: 'Recent games' })
  expect(within(table).getAllByRole('row')).toHaveLength(3)

  fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'blitz' } })

  expect(within(screen.getByRole('table', { name: 'Recent games' })).getByText('Blitz rival')).toBeInTheDocument()
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
