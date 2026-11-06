import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SettingsProvider } from '../settings/SettingsProvider'
import { ThemeProvider } from '../theme/ThemeProvider'
import { ToastProvider } from '../ui'
import { DEFAULT_SETTINGS, EMPTY_TENDENCIES, PROFILE, fakeApi } from '../test/fakes'
import { ProfilePage } from './ProfilePage'

function setup(api = fakeApi()) {
  const onSaved = vi.fn()
  render(
    <MemoryRouter>
      <ThemeProvider>
        <ToastProvider>
          <SettingsProvider api={api} enabled>
            <ProfilePage api={api} profile={PROFILE} onSaved={onSaved} onLoggedOut={vi.fn()} />
          </SettingsProvider>
        </ToastProvider>
      </ThemeProvider>
    </MemoryRouter>,
  )
  return { api, onSaved }
}

const REPORT = {
  ...EMPTY_TENDENCIES,
  games_analyzed: 7,
  provisional: false,
  tendencies: [
    { theme: 'hung_piece', label: 'Leaving pieces undefended', rate_per_game: 1.2, score: 2.4, trend: null,
      games_seen: 5, provisional: false, recent_example: { game_id: 'g', move_number: 12, move_san: 'Nf3' } },
    { theme: 'king_safety', label: 'King safety', rate_per_game: 0.5, score: 1.2, trend: null,
      games_seen: 3, provisional: false, recent_example: { game_id: 'g', move_number: 20, move_san: 'g4' } },
  ],
}  // prettier-ignore

test('the heading shows the player, their rating and games analyzed', async () => {
  setup(fakeApi({ tendencies: vi.fn(async () => REPORT) }))

  expect(screen.getByRole('heading', { level: 1, name: PROFILE.name })).toBeInTheDocument()
  expect(await screen.findByText(/7 games analyzed/)).toBeInTheDocument()
})

test('tendencies are listed with how many games they appeared in', async () => {
  setup(fakeApi({ tendencies: vi.fn(async () => REPORT) }))

  const section = await screen.findByRole('region', { name: 'Your tendencies' })
  expect(await within(section).findByText('Leaving pieces undefended')).toBeInTheDocument()
  expect(within(section).getByText('5 games')).toBeInTheDocument()
})

test('the appearance setting changes the theme at once', async () => {
  const { api } = setup()
  await vi.waitFor(() => expect(api.settings).toHaveBeenCalled())
  const appearance = screen.getByRole('group', { name: 'Appearance' })
  expect(within(appearance).getByLabelText('Light')).toBeChecked()

  fireEvent.click(within(appearance).getByLabelText('Dark'))

  expect(document.documentElement.dataset.theme).toBe('dark')
  fireEvent.click(within(appearance).getByLabelText('Light'))
  expect(document.documentElement.dataset.theme).toBe('light')
})

test('cancel puts back what was saved; the playstyle counter follows the text', () => {
  setup()
  const name = screen.getByLabelText('Display name')
  fireEvent.change(name, { target: { value: 'Someone else' } })
  fireEvent.change(screen.getByLabelText(/How you like to play/), { target: { value: 'Attack!' } })
  expect(screen.getByText('7 / 500')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(name).toHaveValue(PROFILE.name)
})

test('the baseline report opens in a dialog', async () => {
  const report = { text: '## Overview\nYou are a steady player. More detail follows.', created_at: '2026-10-20T10:00:00Z', game_ids: [], invalid_moves_removed: [] }
  setup(fakeApi({ baselineReport: vi.fn(async () => report) }))

  const card = await screen.findByRole('region', { name: 'Baseline report' })
  expect(await within(card).findByText('You are a steady player.')).toBeInTheDocument()
  fireEvent.click(within(card).getByRole('button', { name: 'Read the report' }))

  expect(screen.getByRole('dialog', { name: 'Your baseline report' })).toHaveTextContent('More detail follows.')
})

test('settings are saved per player and applied at once', async () => {
  const { api } = setup()
  await vi.waitFor(() => expect(api.settings).toHaveBeenCalled())

  fireEvent.click(screen.getByLabelText('Pale blue'))
  fireEvent.click(screen.getByLabelText('Merida'))
  fireEvent.click(screen.getByLabelText('Sounds on move'))

  expect(document.documentElement.dataset.board).toBe('pale')
  expect(document.documentElement.dataset.pieces).toBe('merida')
  expect(api.updateSettings).toHaveBeenCalledWith({ board_scheme: 'pale' })
  expect(api.updateSettings).toHaveBeenCalledWith({ piece_set: 'merida' })
  expect(api.updateSettings).toHaveBeenCalledWith({ sounds: true })
})

test('the saved theme is applied when settings load', async () => {
  setup(fakeApi({ settings: vi.fn(async () => ({ ...DEFAULT_SETTINGS, theme: 'dark' as const })) }))

  await vi.waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
  expect(within(screen.getByRole('group', { name: 'Appearance' })).getByLabelText('Dark')).toBeChecked()
})

test('a failed save is undone and reported', async () => {
  const api = fakeApi({ updateSettings: vi.fn(async () => { throw new Error('offline') }) })
  setup(api)
  await vi.waitFor(() => expect(api.settings).toHaveBeenCalled())

  fireEvent.click(screen.getByLabelText('Soft blue'))

  expect(await screen.findByRole('alert')).toHaveTextContent("Your setting couldn't be saved")
  expect(screen.getByLabelText('Baby blue')).toBeChecked()
})

test("a change made before the saved settings arrive isn't undone by them", async () => {
  let arrive: (value: typeof DEFAULT_SETTINGS) => void = () => {}
  const api = fakeApi({ settings: vi.fn(() => new Promise<typeof DEFAULT_SETTINGS>((resolve) => { arrive = resolve })) })
  setup(api)

  fireEvent.click(within(screen.getByRole('group', { name: 'Appearance' })).getByLabelText('Dark'))
  arrive({ ...DEFAULT_SETTINGS, theme: 'light', piece_set: 'merida' })

  await vi.waitFor(() => expect(document.documentElement.dataset.pieces).toBe('merida'))
  expect(document.documentElement.dataset.theme).toBe('dark')
})

test('the coach detail level and playback speed are settings', async () => {
  const { api } = setup()
  await vi.waitFor(() => expect(api.settings).toHaveBeenCalled())

  fireEvent.click(within(screen.getByRole('group', { name: 'Coach detail level' })).getByLabelText('Plain'))
  fireEvent.change(screen.getByLabelText(/Line playback speed/), { target: { value: '2.5' } })

  expect(api.updateSettings).toHaveBeenCalledWith({ coach_detail_level: 'plain' })
  expect(api.updateSettings).toHaveBeenCalledWith({ playback_seconds: 2.5 })
  expect(screen.getByText(/Plain: everyday words/)).toBeInTheDocument()
})

// The card remounts once saved settings load, so it is looked up again each time.
const accounts = () => screen.getByRole('form', { name: 'Your online accounts' })

test('the saved usernames load into the accounts card and a change is saved trimmed', async () => {
  const api = fakeApi({ settings: vi.fn(async () => ({ ...DEFAULT_SETTINGS, lichess_username: 'alex_l' })) })
  setup(api)
  await vi.waitFor(() => expect(within(accounts()).getByLabelText('Lichess username')).toHaveValue('alex_l'))
  expect(within(accounts()).getByRole('button', { name: 'Save usernames' })).toBeDisabled()

  fireEvent.change(within(accounts()).getByLabelText('Chess.com username'), { target: { value: ' nander100 ' } })
  fireEvent.click(within(accounts()).getByRole('button', { name: 'Save usernames' }))

  expect(api.updateSettings).toHaveBeenCalledWith({ chesscom_username: 'nander100', lichess_username: 'alex_l' })
  expect(await within(accounts()).findByRole('status')).toHaveTextContent('Saved')
})

test('a username with other characters is refused before saving', async () => {
  const { api } = setup()
  await vi.waitFor(() => expect(api.settings).toHaveBeenCalled())
  await screen.findByRole('form', { name: 'Your online accounts' })

  fireEvent.change(within(accounts()).getByLabelText('Chess.com username'), { target: { value: 'nander 100' } })

  expect(within(accounts()).getByText('Use only letters, numbers, "_" and "-".')).toBeInTheDocument()
  expect(within(accounts()).getByRole('button', { name: 'Save usernames' })).toBeDisabled()
})
