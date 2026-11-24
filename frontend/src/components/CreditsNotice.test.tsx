import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { Billing } from '../api/types'
import { CreditsCard } from '../pages/CreditsCard'
import { SettingsProvider } from '../settings/SettingsProvider'
import { BILLING, fakeApi } from '../test/fakes'
import { CreditsNotice } from './CreditsNotice'

function notice(billing: Billing) {
  const api = fakeApi({ billing: vi.fn(async () => billing) })
  render(
    <MemoryRouter>
      <CreditsNotice api={api} variant="banner" />
    </MemoryRouter>,
  )
  return api
}

test('nothing shows while credits are fine', async () => {
  const api = notice(BILLING)

  await vi.waitFor(() => expect(api.billing).toHaveBeenCalled())
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('running low says how many credits are left and links to them', async () => {
  notice({ ...BILLING, credits: 4.5, low: true })

  const status = await screen.findByRole('status')
  expect(status).toHaveTextContent('You have 4.5 coaching credits left.')
  expect(within(status).getByRole('link', { name: 'See your credits' })).toHaveAttribute('href', '/profile#credits')
})

test('out of credits says the coach is paused but analysis still works', async () => {
  notice({ ...BILLING, credits: -0.3, low: true, out: true })

  expect(await screen.findByRole('status')).toHaveTextContent(/out of coaching credits.*Analysis still works/)
})

test('an unmetered account never sees a warning', async () => {
  const api = notice({ ...BILLING, credits: 0, low: true, out: true, unmetered: true })

  await vi.waitFor(() => expect(api.billing).toHaveBeenCalled())
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

function card(billing: Billing) {
  const api = fakeApi({ billing: vi.fn(async () => billing) })
  render(
    <MemoryRouter>
      <SettingsProvider api={api} enabled>
        <CreditsCard api={api} />
      </SettingsProvider>
    </MemoryRouter>,
  )
  return api
}

test('the credits card shows the balance in games and the history', async () => {
  card(BILLING)

  const section = await screen.findByRole('region', { name: 'Coaching credits' })
  expect(await within(section).findByText(/42 credits left, about 12 games at Standard/)).toBeInTheDocument()
  expect(within(section).getByText(/about 3.6 times faster/)).toBeInTheDocument()
  expect(within(section).getByRole('list', { name: 'Recent credit changes' })).toHaveTextContent('Free trial+50')
})

test('choosing Deep saves the coach strength', async () => {
  const api = card(BILLING)
  await screen.findByText(/credits left/)

  fireEvent.click(screen.getByLabelText('Deep'))

  await vi.waitFor(() => expect(api.updateSettings).toHaveBeenCalledWith({ coach_strength: 'deep' }))
})
