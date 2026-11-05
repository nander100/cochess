import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ThemeProvider } from '../theme/ThemeProvider'
import { EMPTY_TENDENCIES, PROFILE, fakeApi } from '../test/fakes'
import { ProfilePage } from './ProfilePage'

function setup(api = fakeApi()) {
  const onSaved = vi.fn()
  render(
    <MemoryRouter>
      <ThemeProvider>
        <ProfilePage api={api} profile={PROFILE} onSaved={onSaved} onLoggedOut={vi.fn()} />
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

test('the appearance setting changes the theme at once', () => {
  setup()
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
