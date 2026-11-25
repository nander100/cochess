import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import type { OwnerApi } from '../api/ownerTypes'
import { ThemeProvider } from '../theme/ThemeProvider'
import { ToastProvider } from '../ui'
import { OVERVIEW, PLAYER_DETAIL, PLAYER_ROW, WAITING_ROW, fakeOwnerApi } from '../test/ownerFakes'
import { OwnerArea } from './OwnerPage'

function Where() {
  const location = useLocation()
  return <output data-testid="where">{location.pathname + location.search}</output>
}

function setup(api: OwnerApi = fakeOwnerApi(), url = '/owner') {
  render(
    <MemoryRouter initialEntries={[url]}>
      <ThemeProvider>
        <ToastProvider>
          <Routes>
            <Route path="/owner/*" element={<OwnerArea api={api} />} />
          </Routes>
          <Where />
        </ToastProvider>
      </ThemeProvider>
    </MemoryRouter>,
  )
  return api
}

const where = () => screen.getByTestId('where').textContent

test('the overview shows the money, players and paid vs unpaid, and the period is in the address', async () => {
  const api = setup()

  const money = await screen.findByRole('region', { name: 'Money' })
  expect(within(money).getByText('$132.50')).toBeInTheDocument()
  expect(within(money).getByText('$41.25')).toBeInTheDocument()
  expect(within(money).getByText('$91.25')).toBeInTheDocument()
  expect(within(money).getByText('cache hit rate 62%')).toBeInTheDocument()
  const plans = screen.getByRole('region', { name: 'Paid and unpaid' })
  expect(within(plans).getByText('At zero credits').nextSibling).toHaveTextContent('6')
  expect(screen.getByRole('region', { name: 'Activity' })).toHaveTextContent('Coach calls4101,600')

  fireEvent.click(screen.getByLabelText('This month'))

  await waitFor(() => expect(api.overview).toHaveBeenLastCalledWith('month'))
  expect(where()).toBe('/owner?tab=overview&period=month')
})

test('a loss shows in the danger color, next to its label', async () => {
  const loss = { ...OVERVIEW.money, difference_microusd: -3_000_000 }
  setup(fakeOwnerApi({ overview: vi.fn(async () => ({ ...OVERVIEW, money: loss })) }))

  const value = await screen.findByText('-$3.00')
  expect(value).toHaveClass('owner-loss')
  expect(value.previousSibling).toHaveTextContent('Difference')
})

test('an overview error can be retried', async () => {
  const overview = vi.fn().mockRejectedValueOnce(new Error('The server is down.')).mockResolvedValue(OVERVIEW)
  setup(fakeOwnerApi({ overview }))

  fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

  expect(await screen.findByRole('region', { name: 'Money' })).toBeInTheDocument()
  expect(overview).toHaveBeenCalledTimes(2)
})

test('the players table searches, filters, sorts and pages through the server', async () => {
  const players = vi.fn(async () => ({ rows: [PLAYER_ROW], total: 120, page: 1, page_size: 50 }))
  setup(fakeOwnerApi({ players }), '/owner?tab=players')

  const table = await screen.findByRole('table', { name: 'Players' })
  expect(within(table).getByRole('link', { name: 'Ana Rivera' })).toHaveAttribute('href', '/owner/players/p-ana')
  expect(within(table).getByText('214.3')).toBeInTheDocument() // balance, in credits
  expect(within(table).getByText('$1.18')).toBeInTheDocument() // API cost, 30 days

  fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'ana' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  await waitFor(() => expect(players).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'ana', page: 1 })))

  fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'trial' } })
  await waitFor(() => expect(players).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'ana', plan: 'trial' })))

  fireEvent.click(await screen.findByRole('button', { name: /API cost, 30 days/ }))
  await waitFor(() => expect(players).toHaveBeenLastCalledWith(expect.objectContaining({ sort: '-cost' })))
  expect(await screen.findByRole('columnheader', { name: /API cost/ })).toHaveAttribute('aria-sort', 'descending')

  fireEvent.click(await screen.findByRole('button', { name: 'Next' }))
  await waitFor(() => expect(players).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })))
  expect(where()).toBe('/owner?tab=players&q=ana&plan=trial&sort=-cost&page=2')
})

test('players filters in the address are used, and unknown ones are dropped', async () => {
  const players = vi.fn(async () => ({ rows: [], total: 0, page: 1, page_size: 50 }))
  setup(fakeOwnerApi({ players }), '/owner?tab=players&status=suspended&plan=gold&sort=drop&zero_credits=true')

  expect(await screen.findByRole('heading', { name: 'No players match' })).toBeInTheDocument()
  expect(players).toHaveBeenCalledWith({
    q: undefined,
    status: 'suspended',
    plan: undefined,
    strength: undefined,
    zero_credits: true,
    sort: undefined,
    page: 1,
  })
})

test('the waitlist accepts one player or a selection, after confirming', async () => {
  const second = { ...WAITING_ROW, id: 'p-cy', name: 'Cy Lam', email: 'cy@example.com' }
  const players = vi.fn(async () => ({ rows: [WAITING_ROW, second], total: 2, page: 1, page_size: 50 }))
  const acceptMany = vi.fn(async (ids: string[]) => ({ accepted: ids.length, skipped: [] }))
  setup(fakeOwnerApi({ players, acceptMany }), '/owner?tab=waitlist')

  const table = await screen.findByRole('table', { name: 'Waitlist' })
  expect(players).toHaveBeenCalledWith({ status: 'waitlisted', sort: 'waited', page: 1 })
  expect(screen.getByRole('button', { name: 'Accept selected (0)' })).toBeDisabled()

  fireEvent.click(within(table).getByRole('button', { name: 'Accept Ben Okafor' }))
  const one = screen.getByRole('dialog', { name: 'Accept Ben Okafor?' })
  fireEvent.click(within(one).getByRole('button', { name: 'Cancel' }))
  expect(acceptMany).not.toHaveBeenCalled()

  fireEvent.click(within(table).getByLabelText('Select everyone on this page'))
  fireEvent.click(screen.getByRole('button', { name: 'Accept selected (2)' }))
  const many = screen.getByRole('dialog', { name: 'Accept 2 players?' })
  expect(within(many).getByText('Cy Lam')).toBeInTheDocument()
  fireEvent.click(within(many).getByRole('button', { name: 'Accept' }))

  await waitFor(() => expect(acceptMany).toHaveBeenCalledWith(['p-ben', 'p-cy']))
  expect(await screen.findByText('Accepted 2 players.')).toBeInTheDocument()
  await waitFor(() => expect(players).toHaveBeenCalledTimes(2)) // reloaded
})

test('an empty waitlist says what happens next', async () => {
  const players = vi.fn(async () => ({ rows: [], total: 0, page: 1, page_size: 50 }))
  setup(fakeOwnerApi({ players }), '/owner?tab=waitlist')

  expect(await screen.findByRole('heading', { name: 'Nobody is waiting' })).toBeInTheDocument()
})

test("a player's page shows their numbers, ledger, subscription and audit log", async () => {
  const api = setup(undefined, '/owner/players/p-ana')

  expect(await screen.findByRole('heading', { name: 'Ana Rivera' })).toBeInTheDocument()
  expect(api.player).toHaveBeenCalledWith('p-ana')
  const numbers = screen.getByRole('region', { name: 'Numbers' })
  expect(within(numbers).getByText('214.3 credits')).toBeInTheDocument()
  expect(within(numbers).getByText('164.3 allowance · 50 lasting')).toBeInTheDocument()
  const audit = screen.getByRole('list', { name: 'Audit log' })
  expect(within(audit).getByText('Added 50 credits: Beta tester')).toBeInTheDocument()
  expect(within(audit).getByText(/by CLI/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open the customer in Stripe' })).toHaveAttribute(
    'href',
    PLAYER_DETAIL.billing_dashboard_url,
  )
  const ledger = screen.getByRole('table', { name: 'Credit ledger' })
  expect(within(ledger).getByText('+50')).toBeInTheDocument()
  expect(within(ledger).getByText('Monthly allowance')).toBeInTheDocument()
})

test('revoking needs a reason and offers to cancel a live subscription, unticked', async () => {
  const api = setup(undefined, '/owner/players/p-ana')
  fireEvent.click(await screen.findByRole('button', { name: 'Revoke access' }))

  const dialog = screen.getByRole('dialog', { name: "Revoke Ana Rivera's access?" })
  expect(within(dialog).getByRole('button', { name: 'Revoke access' })).toBeDisabled()
  const cancel = within(dialog).getByLabelText('Also cancel their subscription in Stripe now')
  expect(cancel).not.toBeChecked()

  fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: 'Chargeback fraud' } })
  fireEvent.click(cancel)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke and cancel' }))

  await waitFor(() =>
    expect(api.suspend).toHaveBeenCalledWith('p-ana', {
      reason: 'Chargeback fraud',
      tell_reason: false,
      cancel_subscription: true,
    }),
  )
  expect(await screen.findByRole('button', { name: 'Restore access' })).toBeInTheDocument()
})

test('without a subscription, revoking never asks about one', async () => {
  const detail = { ...PLAYER_DETAIL, subscription_status: null }
  setup(fakeOwnerApi({ player: vi.fn(async () => detail) }), '/owner/players/p-ana')
  fireEvent.click(await screen.findByRole('button', { name: 'Revoke access' }))

  expect(screen.queryByLabelText(/cancel their subscription/)).not.toBeInTheDocument()
})

test('removing credits sends a negative amount with the note, and a refusal stays in the dialog', async () => {
  const changeCredits = vi
    .fn()
    .mockRejectedValueOnce(new Error('the note is longer than 200 characters'))
    .mockResolvedValue(PLAYER_DETAIL)
  setup(fakeOwnerApi({ changeCredits }), '/owner/players/p-ana')
  fireEvent.click(await screen.findByRole('button', { name: 'Add or remove credits' }))

  const dialog = screen.getByRole('dialog', { name: 'Credits for Ana Rivera' })
  fireEvent.click(within(dialog).getByLabelText('Remove'))
  fireEvent.change(within(dialog).getByLabelText('Credits'), { target: { value: '5' } })
  expect(within(dialog).getByRole('button', { name: 'Remove 5 credits' })).toBeDisabled() // no note yet
  fireEvent.change(within(dialog).getByLabelText(/Note/), { target: { value: 'Correction' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Remove 5 credits' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent('the note is longer than 200 characters')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Remove 5 credits' }))
  await waitFor(() => expect(changeCredits).toHaveBeenLastCalledWith('p-ana', -5, 'Correction', false))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})

test('metering and acceptance are confirmed before they happen', async () => {
  const detail = { ...PLAYER_DETAIL, row: WAITING_ROW, subscription_status: null }
  const api = setup(fakeOwnerApi({ player: vi.fn(async () => detail) }), '/owner/players/p-ben')

  fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))
  expect(api.accept).not.toHaveBeenCalled()
  const dialog = screen.getByRole('dialog', { name: 'Accept Ben Okafor?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Accept' }))
  await waitFor(() => expect(api.accept).toHaveBeenCalledWith('p-ben'))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

  fireEvent.click(screen.getByRole('button', { name: 'Never charge' }))
  expect(api.setMetering).not.toHaveBeenCalled()
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Never charge' }))
  await waitFor(() => expect(api.setMetering).toHaveBeenCalledWith('p-ben', true))
})
