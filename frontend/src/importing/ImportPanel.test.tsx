import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ApiError } from '../api/client'
import type { UserSettings } from '../api/types'
import { SettingsContext } from '../settings/settingsContext'
import { DEFAULT_SETTINGS, DETAIL, GAME, fakeDeps, importRow } from '../test/fakes'
import { ToastProvider } from '../ui'
import { ImportPanel } from './ImportPanel'

function setup(deps = fakeDeps(), settings: Partial<UserSettings> = { chesscom_username: 'nander100' }) {
  const onAdded = vi.fn()
  render(
    <MemoryRouter>
      <ToastProvider>
        <SettingsContext.Provider value={{ settings: { ...DEFAULT_SETTINGS, ...settings }, loaded: true, update: vi.fn() }}>
          <ImportPanel deps={deps} onLoggedOut={vi.fn()} onAdded={onAdded} />
        </SettingsContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  )
  return { deps, onAdded }
}

const FOUND = {
  platform: 'chesscom' as const,
  username: 'nander100',
  games_left_today: 10,
  games: [importRow(0), importRow(1, { already_imported: true }), importRow(2, { user_color: null })],
}

test('without a username the panel points to the profile', () => {
  setup(fakeDeps(), {})

  expect(screen.getByRole('link', { name: 'Add your Chess.com or Lichess username' })).toHaveAttribute('href', '/profile')
})

test('fetched games are reviewed: added ones are marked, unknown colors are asked for', async () => {
  const deps = fakeDeps({ importGames: vi.fn(async () => FOUND) })
  setup(deps)

  fireEvent.change(screen.getByLabelText('Time control'), { target: { value: 'rapid' } })
  fireEvent.click(screen.getByRole('button', { name: 'Fetch games' }))

  const table = await screen.findByRole('table', { name: 'Fetched games' })
  expect(deps.api.importGames).toHaveBeenCalledWith({ platform: 'chesscom', max: 20, tc: 'rapid', since: null })
  expect(within(table).getByText('Already added')).toBeInTheDocument()
  expect(within(table).getByText('From your username')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Choose your color for 1 game' })).toBeDisabled()

  fireEvent.change(within(table).getByLabelText('Your color in me vs Rival2'), { target: { value: 'black' } })

  expect(screen.getByRole('button', { name: 'Add and analyze 2 games' })).toBeEnabled()
})

test('ticked games are added with their platform ids, then analyzed', async () => {
  const deps = fakeDeps({
    importGames: vi.fn(async () => ({ ...FOUND, games: [importRow(0), importRow(3)] })),
    getGame: vi.fn(async () => DETAIL),
  })
  const { onAdded } = setup(deps)
  fireEvent.click(screen.getByRole('button', { name: 'Fetch games' }))
  const table = await screen.findByRole('table', { name: 'Fetched games' })
  fireEvent.click(within(table).getByLabelText('Add me vs Rival3'))

  fireEvent.click(screen.getByRole('button', { name: 'Add and analyze 1 game' }))

  expect(await screen.findByText('Added and analyzed 1 game.')).toBeInTheDocument()
  expect(deps.api.createGame).toHaveBeenCalledTimes(1)
  expect(vi.mocked(deps.api.createGame).mock.calls[0][0]).toMatchObject({
    user_color: 'white',
    external: { platform: 'chesscom', external_id: '1000' },
  })
  expect(deps.api.getGame).toHaveBeenCalled()
  expect(onAdded).toHaveBeenCalled()
})

test("a platform's refusal is shown next to the form", async () => {
  const notFound = new ApiError(404, 'Chess.com has no player called nander100. Check the username on your profile.')
  setup(fakeDeps({ importGames: vi.fn(async () => Promise.reject(notFound)) }))

  fireEvent.click(screen.getByRole('button', { name: 'Fetch games' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('has no player called nander100')
})

test("only today's room is added; the rest waits for tomorrow", async () => {
  const deps = fakeDeps({
    importGames: vi.fn(async () => ({ ...FOUND, games_left_today: 1, games: [importRow(0), importRow(3)] })),
    getGame: vi.fn(async () => DETAIL),
  })
  setup(deps)
  fireEvent.click(screen.getByRole('button', { name: 'Fetch games' }))
  await screen.findByRole('table', { name: 'Fetched games' })

  expect(screen.getByText('Only 1 more game can be added today, so the first one ticked will be added.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Add and analyze 1 game' }))

  expect(await screen.findByText(/Added and analyzed 1 game\. Today's limit is reached: import the other 1 game tomorrow\./)).toBeInTheDocument()
  expect(deps.api.createGame).toHaveBeenCalledTimes(1)
})

test('a cap reached during the batch stops adding but keeps and analyzes what was added', async () => {
  const capped = new ApiError(429, 'CoChess analyzes at most 10 new games a day per player while in testing.')
  const deps = fakeDeps({
    importGames: vi.fn(async () => ({ ...FOUND, games: [importRow(0), importRow(3), importRow(4)] })),
    createGame: vi.fn()
      .mockResolvedValueOnce({ ...GAME, game_id: 'g1' })
      .mockRejectedValueOnce(capped),
    getGame: vi.fn(async () => DETAIL),
  })
  setup(deps)
  fireEvent.click(screen.getByRole('button', { name: 'Fetch games' }))
  await screen.findByRole('table', { name: 'Fetched games' })

  fireEvent.click(screen.getByRole('button', { name: 'Add and analyze 3 games' }))

  expect(await screen.findByText(/Added and analyzed 1 game\. Today's limit is reached: import the other 2 games tomorrow\./)).toBeInTheDocument()
  expect(deps.api.createGame).toHaveBeenCalledTimes(2)
  expect(deps.api.getGame).toHaveBeenCalledWith('g1')
})
