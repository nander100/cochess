import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useParams } from 'react-router'
import { ApiError } from '../api/client'
import type { UserSettings } from '../api/types'
import { SettingsContext } from '../settings/settingsContext'
import { DEFAULT_SETTINGS, fakeDeps, importRow } from '../test/fakes'
import { ToastProvider } from '../ui'
import { LatestGameCard } from './LatestGameCard'

function Opened() {
  return <p>opened {useParams().gameId}</p>
}

function setup(deps = fakeDeps(), settings: Partial<UserSettings> = { chesscom_username: 'nander100' }) {
  render(
    <MemoryRouter initialEntries={['/games']}>
      <ToastProvider>
        <SettingsContext.Provider value={{ settings: { ...DEFAULT_SETTINGS, ...settings }, loaded: true, update: vi.fn() }}>
          <Routes>
            <Route path="/games" element={<LatestGameCard deps={deps} onLoggedOut={vi.fn()} />} />
            <Route path="/games/:gameId" element={<Opened />} />
          </Routes>
        </SettingsContext.Provider>
      </ToastProvider>
    </MemoryRouter>,
  )
  return deps
}

const analyze = () => fireEvent.click(screen.getByRole('button', { name: 'Analyze my latest game' }))

test('without a username the card points to the profile', () => {
  setup(fakeDeps(), {})

  expect(screen.getByRole('link', { name: 'Add your Chess.com or Lichess username' })).toHaveAttribute('href', '/profile')
  expect(screen.queryByRole('button', { name: 'Analyze my latest game' })).not.toBeInTheDocument()
})

test('with both accounts it says the newer game is used', () => {
  setup(fakeDeps(), { chesscom_username: 'nander100', lichess_username: 'alex_l' })

  expect(
    screen.getByText('Analyze your latest game from Chess.com (nander100) or Lichess (alex_l), whichever you played last.'),
  ).toBeInTheDocument()
})

test('one click adds the latest game with its platform id, analyzes it, and opens it', async () => {
  const deps = setup()

  analyze()

  expect(await screen.findByText('opened game-1')).toBeInTheDocument()
  expect(deps.api.latestGame).toHaveBeenCalled()
  expect(vi.mocked(deps.api.createGame).mock.calls[0][0]).toEqual({
    pgn: importRow(0).pgn,
    user_color: 'white',
    external: { platform: 'chesscom', external_id: '1000' },
  })
})

test('a game already here just opens', async () => {
  const deps = setup(
    fakeDeps({ latestGame: vi.fn(async () => ({ game: importRow(0, { already_imported: true }), existing_game_id: 'old-7' })) }),
  )

  analyze()

  expect(await screen.findByText('opened old-7')).toBeInTheDocument()
  expect(deps.api.createGame).not.toHaveBeenCalled()
})

test('a latest game without the username asks for a paste instead of guessing', async () => {
  const deps = setup(
    fakeDeps({ latestGame: vi.fn(async () => ({ game: importRow(0, { user_color: null }), existing_game_id: null })) }),
  )

  analyze()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Your username isn't in your latest Chess.com game (me vs Rival0). Paste it below and choose your color.",
  )
  expect(deps.api.createGame).not.toHaveBeenCalled()
})

test("a platform's refusal is shown on the card", async () => {
  const notFound = new ApiError(404, 'No games found on Chess.com (nander100).')
  setup(fakeDeps({ latestGame: vi.fn(async () => Promise.reject(notFound)) }))

  analyze()

  expect(await screen.findByRole('alert')).toHaveTextContent('No games found on Chess.com (nander100).')
})
