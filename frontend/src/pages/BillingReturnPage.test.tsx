import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import type { Billing } from '../api/types'
import { BILLING, fakeApi } from '../test/fakes'
import { BillingReturnPage, POLL_MS, POLL_TRIES } from './BillingReturnPage'

const NOW = Date.parse('2026-11-24T12:00:00Z')
const TOP_UP = { kind: 'top_up' as const, credits: 150, note: null, created_at: '2026-11-24T12:00:05Z' }
const OLD_TOP_UP = { ...TOP_UP, created_at: '2026-11-20T12:00:00Z' }

function page(responses: Billing[], product = 'top_up') {
  const billing = vi.fn(async () => responses[Math.min(billing.mock.calls.length - 1, responses.length - 1)])
  const api = fakeApi({ billing })
  render(
    <MemoryRouter initialEntries={[`/billing/return?product=${product}`]}>
      <BillingReturnPage api={api} now={() => NOW} />
    </MemoryRouter>,
  )
  return billing
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

test('waits for the webhook, then shows the credits that arrived', async () => {
  const before = { ...BILLING, history: [OLD_TOP_UP] }
  const after = { ...BILLING, credits: 192, history: [TOP_UP, OLD_TOP_UP] }
  const billing = page([before, after])

  await act(async () => {})
  expect(screen.getByText(/Your credits will appear in a moment/)).toBeInTheDocument()
  await act(async () => vi.advanceTimersByTime(POLL_MS))

  expect(screen.getByRole('status')).toHaveTextContent('150 credits added. You now have 192 coaching credits.')
  expect(billing).toHaveBeenCalledTimes(2)
})

test('a subscription waits for its allowance, not an older top-up', async () => {
  const allowance = { ...TOP_UP, kind: 'allowance' as const, credits: 300 }
  page([{ ...BILLING, history: [TOP_UP] }, { ...BILLING, history: [allowance, TOP_UP] }], 'monthly')

  await act(async () => {})
  expect(screen.getByText(/in a moment/)).toBeInTheDocument()
  await act(async () => vi.advanceTimersByTime(POLL_MS))

  expect(screen.getByRole('status')).toHaveTextContent('300 credits added')
})

test('stops asking after a while and says the credits are on their way', async () => {
  const billing = page([{ ...BILLING, history: [] }])

  await act(async () => {})
  for (let i = 1; i < POLL_TRIES; i++) await act(async () => vi.advanceTimersByTime(POLL_MS))

  expect(screen.getByRole('status')).toHaveTextContent('taking longer than usual')
  expect(billing).toHaveBeenCalledTimes(POLL_TRIES)
})
