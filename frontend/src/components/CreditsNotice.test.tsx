import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { type ApiClient, ApiError } from '../api/client'
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

function card(billing: Billing, redirect = vi.fn(), overrides: Partial<ApiClient> = {}) {
  const api = fakeApi({ billing: vi.fn(async () => billing), ...overrides })
  render(
    <MemoryRouter>
      <SettingsProvider api={api} enabled>
        <CreditsCard api={api} redirect={redirect} />
      </SettingsProvider>
    </MemoryRouter>,
  )
  return api
}

test('subscribing goes to Stripe, and the buttons stay off while the browser leaves', async () => {
  const redirect = vi.fn()
  card(BILLING, redirect)

  fireEvent.click(await screen.findByRole('button', { name: 'Subscribe: $10 a month for 300 credits' }))

  await vi.waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe.test/checkout/monthly'))
  expect(screen.getByRole('button', { name: 'Buy 150 credits for $5' })).toBeDisabled()
  expect(screen.getByText(/Prices are before tax/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Receipts|Manage/ })).not.toBeInTheDocument()
})

test('buying credits goes to Stripe for the top-up', async () => {
  const redirect = vi.fn()
  const api = card(BILLING, redirect)

  fireEvent.click(await screen.findByRole('button', { name: 'Buy 150 credits for $5' }))

  await vi.waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe.test/checkout/top_up'))
  expect(api.checkout).toHaveBeenCalledWith('top_up')
})

test('a subscriber sees renewal and manage, not a second subscribe', async () => {
  const redirect = vi.fn()
  const subscribed: Billing = {
    ...BILLING,
    has_billing_account: true,
    subscription: { status: 'active', period_end: '2026-12-24T00:00:00Z' },
  }
  const api = card(subscribed, redirect)

  fireEvent.click(await screen.findByRole('button', { name: 'Manage subscription' }))

  await vi.waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe.test/portal'))
  expect(api.billingPortal).toHaveBeenCalled()
  expect(screen.getByText(/Your subscription renews on/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Subscribe/ })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Buy 150 credits for $5' })).toBeInTheDocument()
})

test('a failed renewal asks for a card update; players under 18 see the guardian note', async () => {
  card({
    ...BILLING,
    has_billing_account: true,
    subscription: { status: 'past_due', period_end: null },
    needs_guardian: true,
  })

  expect(await screen.findByText(/Your last payment didn't go through/)).toBeInTheDocument()
  expect(screen.getByText(/need a parent or guardian to pay/)).toBeInTheDocument()
})

test('no payment buttons while payments are off', async () => {
  card({ ...BILLING, payments_enabled: false })

  await screen.findByText(/credits left/)
  expect(screen.queryByRole('button', { name: /Subscribe|Buy/ })).not.toBeInTheDocument()
})

test('a checkout that fails leaves the buttons usable and goes nowhere', async () => {
  const redirect = vi.fn()
  const checkout = vi.fn(async () => {
    throw new ApiError(503, "Payments aren't set up yet.")
  })
  card(BILLING, redirect, { checkout })

  fireEvent.click(await screen.findByRole('button', { name: /Buy 150 credits/ }))

  await vi.waitFor(() => expect(checkout).toHaveBeenCalled())
  await vi.waitFor(() => expect(screen.getByRole('button', { name: /Buy 150 credits/ })).toBeEnabled())
  expect(redirect).not.toHaveBeenCalled()
})

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
