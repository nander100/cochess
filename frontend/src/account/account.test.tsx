import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import type { AccountApi } from '../api/accountTypes'
import { ApiError } from '../api/client'
import { PROFILE, fakeApi } from '../test/fakes'
import { ThemeProvider } from '../theme/ThemeProvider'
import { ToastProvider } from '../ui'
import { DataActions } from './DataActions'
import { EmailCard } from './EmailCard'
import { LegalDocument } from './LegalDocument'
import { TermsPrompt } from './TermsPrompt'
import { UnsubscribePage } from './UnsubscribePage'

function wrap(node: ReactNode, url = '/') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ThemeProvider>
        <ToastProvider>{node}</ToastProvider>
      </ThemeProvider>
    </MemoryRouter>,
  )
}

const account = (overrides: Partial<AccountApi> = {}): AccountApi => ({ ...fakeApi().account, ...overrides })

test('a legal page shows the server text and its version, never raw HTML', async () => {
  const legal = vi.fn(async () => ({
    kind: 'privacy' as const,
    version: '2026-12-01',
    markdown: '# Privacy Policy\n\nWe use Anthropic.\n\n<script>alert(1)</script>',
  }))
  const { container } = wrap(<LegalDocument api={account({ legal })} kind="privacy" />)

  expect(await screen.findByRole('heading', { name: 'Privacy Policy' })).toBeInTheDocument()
  expect(screen.getByText('We use Anthropic.')).toBeInTheDocument()
  expect(screen.getByText('Version 2026-12-01')).toBeInTheDocument()
  expect(container.querySelector('script')).toBeNull()
  expect(legal).toHaveBeenCalledWith('privacy')
})

test('the terms prompt accepts the version it showed', async () => {
  const api = account()
  const onAccepted = vi.fn()
  const profile = { ...PROFILE, terms_accepted: false }
  wrap(<TermsPrompt api={api} profile={profile} onAccepted={onAccepted} onLogOut={vi.fn()} />)

  expect(screen.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '/terms')
  fireEvent.click(screen.getByRole('button', { name: 'I agree' }))

  await waitFor(() => expect(onAccepted).toHaveBeenCalled())
  expect(api.acceptTerms).toHaveBeenCalledWith(PROFILE.terms_version)
})

test('a refused acceptance stays on the prompt with the reason', async () => {
  const acceptTerms = vi.fn().mockRejectedValue(new ApiError(409, 'These terms have been updated.'))
  const onAccepted = vi.fn()
  const profile = { ...PROFILE, terms_accepted: false, age_band: '13_17' as const }
  wrap(<TermsPrompt api={account({ acceptTerms })} profile={profile} onAccepted={onAccepted} onLogOut={vi.fn()} />)

  expect(screen.getByText(/parent or guardian/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'I agree' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('These terms have been updated.')
  expect(onAccepted).not.toHaveBeenCalled()
})

test('downloading saves the zip the server sent', async () => {
  const save = vi.fn()
  wrap(<DataActions api={account()} name="Alex" onDeleted={vi.fn()} save={save} />)

  fireEvent.click(screen.getByRole('button', { name: 'Download my data' }))

  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.any(Blob), 'cochess-export-2026-11-24.zip'))
})

test('a refused download shows why', async () => {
  const exportData = vi.fn().mockRejectedValue(new ApiError(429, 'Try again in 4 minutes.'))
  wrap(<DataActions api={account({ exportData })} name="Alex" onDeleted={vi.fn()} save={vi.fn()} />)

  fireEvent.click(screen.getByRole('button', { name: 'Download my data' }))

  expect(await screen.findByText('Try again in 4 minutes.')).toBeInTheDocument()
})

test('deleting needs the name typed, then signs out', async () => {
  const api = account()
  const onDeleted = vi.fn()
  wrap(<DataActions api={api} name="Alex" subscribed onDeleted={onDeleted} />)

  fireEvent.click(screen.getByRole('button', { name: 'Delete my account' }))
  const dialog = screen.getByRole('dialog', { name: 'Delete your account?' })
  expect(within(dialog).getByText(/subscription is cancelled straight away/)).toBeInTheDocument()
  const confirm = within(dialog).getByRole('button', { name: 'Delete for good' })
  expect(confirm).toBeDisabled()
  fireEvent.change(within(dialog).getByLabelText(/Type your name/), { target: { value: 'alex ' } })
  fireEvent.click(confirm)

  await waitFor(() => expect(onDeleted).toHaveBeenCalled())
  expect(api.deleteAccount).toHaveBeenCalledWith('alex')
})

test('a refused deletion keeps the dialog open with the reason', async () => {
  const deleteAccount = vi.fn().mockRejectedValue(new ApiError(502, "Stripe didn't cancel the subscription."))
  const onDeleted = vi.fn()
  wrap(<DataActions api={account({ deleteAccount })} name="Alex" onDeleted={onDeleted} />)

  fireEvent.click(screen.getByRole('button', { name: 'Delete my account' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.change(within(dialog).getByLabelText(/Type your name/), { target: { value: 'Alex' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete for good' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent("Stripe didn't cancel")
  expect(onDeleted).not.toHaveBeenCalled()
})

test('each email switch saves its own group', async () => {
  const api = account()
  wrap(<EmailCard api={api} email="alex@example.com" />)

  const added = await screen.findByLabelText(/Credits added/)
  expect(added).toBeChecked()
  expect(screen.getByText(/alex@example.com/)).toBeInTheDocument()
  fireEvent.click(added)

  await waitFor(() => expect(api.updateEmailPreferences).toHaveBeenCalledWith({ credits_added: false }))
  expect(await screen.findByLabelText(/Credits added/)).not.toBeChecked()
})

test('the unsubscribe page turns the email off from the link', async () => {
  const api = account()
  wrap(<UnsubscribePage api={api} />, '/unsubscribe?token=abc.def')

  expect(await screen.findByRole('heading', { name: "You won't get these emails any more." })).toBeInTheDocument()
  expect(api.unsubscribe).toHaveBeenCalledWith('abc.def')
  expect(screen.getByText(/running low on credits/)).toBeInTheDocument()
})

test('a bad unsubscribe link says so', async () => {
  const unsubscribe = vi.fn().mockRejectedValue(new ApiError(400, "This link isn't valid."))
  wrap(<UnsubscribePage api={account({ unsubscribe })} />, '/unsubscribe?token=forged')

  expect(await screen.findByRole('alert')).toHaveTextContent("This link isn't valid.")
})
