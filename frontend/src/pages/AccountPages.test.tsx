import { act, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { ApiError } from '../api/client'
import type { Profile } from '../api/types'
import { PROFILE, fakeApi } from '../test/fakes'
import { ThemeProvider } from '../theme/ThemeProvider'
import { AccountStatusPage, GOOGLE_SIGN_IN, SignInPage, WAITLIST_POLL_MS } from './AccountPages'
import { SignupPage } from './SignupPage'

const WAITING: Profile = {
  ...PROFILE,
  status: 'waitlisted',
  email: 'sam@example.com',
  google_connected: true,
  waitlisted_at: '2026-11-20T10:00:00Z',
}

function wrap(node: ReactNode) {
  return render(
    <MemoryRouter>
      <ThemeProvider>{node}</ThemeProvider>
    </MemoryRouter>,
  )
}

// Signing in

test('signing in goes to Google with a full page load', () => {
  wrap(<SignInPage reason={null} />)

  expect(screen.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute('href', GOOGLE_SIGN_IN)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test.each([
  ['cancelled', /cancelled/],
  ['unverified', /isn't verified/],
  ['expired', /too long/],
  ['something-new', /couldn't sign you in/],
])('a %s sign-in says what happened', (reason, text) => {
  wrap(<SignInPage reason={reason} />)

  expect(screen.getByRole('alert')).toHaveTextContent(text)
  expect(screen.getByRole('link', { name: 'Continue with Google' })).toBeInTheDocument()
})

test('after the age check refuses, there is no button to try again', () => {
  wrap(<SignInPage reason="age" />)

  expect(screen.getByRole('alert')).toHaveTextContent("can't create a CoChess account")
  expect(screen.queryByRole('link', { name: 'Continue with Google' })).not.toBeInTheDocument()
})

// The waitlist and paused pages

test('the waitlist page says who is waiting and where the email will go', () => {
  wrap(<AccountStatusPage api={fakeApi()} profile={WAITING} onActive={vi.fn()} onLogOut={vi.fn()} onDeleted={vi.fn()} />)

  expect(screen.getByRole('heading', { name: `You're on the list, ${WAITING.name}.` })).toBeInTheDocument()
  expect(screen.getByText(/sam@example.com/)).toBeInTheDocument()
  expect(screen.getByText(/Joined/)).toHaveTextContent('2026')
})

test('the waitlist page opens the app once the player is accepted', async () => {
  vi.useFakeTimers()
  try {
    const me = vi.fn().mockResolvedValueOnce(WAITING).mockResolvedValueOnce({ ...WAITING, status: 'active' })
    const onActive = vi.fn()
    wrap(<AccountStatusPage api={fakeApi({ me })} profile={WAITING} onActive={onActive} onLogOut={vi.fn()} onDeleted={vi.fn()} />)

    await act(async () => vi.advanceTimersByTimeAsync(WAITLIST_POLL_MS))
    expect(onActive).not.toHaveBeenCalled()
    await act(async () => vi.advanceTimersByTimeAsync(WAITLIST_POLL_MS))

    expect(onActive).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }))
  } finally {
    vi.useRealTimers()
  }
})

test('a paused account is told so and can sign out, and nothing polls', async () => {
  vi.useFakeTimers()
  try {
    const api = fakeApi()
    const onLogOut = vi.fn()
    const paused: Profile = { ...WAITING, status: 'suspended' }
    wrap(<AccountStatusPage api={api} profile={paused} onActive={vi.fn()} onLogOut={onLogOut} onDeleted={vi.fn()} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Your access is paused.')
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await act(async () => vi.advanceTimersByTimeAsync(WAITLIST_POLL_MS * 2))

    expect(onLogOut).toHaveBeenCalled()
    expect(api.me).not.toHaveBeenCalled()
  } finally {
    vi.useRealTimers()
  }
})

// The sign-up form

async function openSignup(api = fakeApi()) {
  const onJoined = vi.fn()
  wrap(<SignupPage api={api} onJoined={onJoined} />)
  await screen.findByRole('heading', { name: 'Welcome, Sam Player.' })
  return { api, onJoined }
}

test('the age question is neutral and starts empty', async () => {
  await openSignup()

  expect(screen.getByLabelText('What year were you born?')).toHaveValue('')
  expect(screen.queryByText(/\b13\b/)).not.toBeInTheDocument()
  expect(screen.getByRole('checkbox')).not.toBeChecked()
})

test('signing up sends the year and the terms version, then joins', async () => {
  const { api, onJoined } = await openSignup()

  fireEvent.change(screen.getByLabelText('What year were you born?'), { target: { value: '1990' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Join the waitlist' }))

  await vi.waitFor(() => expect(onJoined).toHaveBeenCalled())
  expect(api.signUp).toHaveBeenCalledWith({ birth_year: 1990, accept_terms: true, terms_version: '2026-11-draft' })
})

test('the form asks for a four-digit year and the terms before sending', async () => {
  const { api } = await openSignup()

  fireEvent.click(screen.getByRole('button', { name: 'Join the waitlist' }))
  expect(screen.getByRole('alert')).toHaveTextContent('four digits')
  fireEvent.change(screen.getByLabelText('What year were you born?'), { target: { value: '1990' } })
  fireEvent.click(screen.getByRole('button', { name: 'Join the waitlist' }))
  expect(screen.getByRole('alert')).toHaveTextContent('agree to the terms')

  expect(api.signUp).not.toHaveBeenCalled()
})

test('too young: a friendly refusal and the form is gone', async () => {
  await openSignup(fakeApi({ signUp: vi.fn(async () => Promise.reject(new ApiError(403, 'no'))) }))

  fireEvent.change(screen.getByLabelText('What year were you born?'), { target: { value: '2020' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Join the waitlist' }))

  expect(await screen.findByRole('heading', { name: /can't create a CoChess account yet/ })).toBeInTheDocument()
  expect(screen.queryByLabelText('What year were you born?')).not.toBeInTheDocument()
})

test('a sign-up that took too long asks to start again with Google', async () => {
  const api = fakeApi({ signupInfo: vi.fn(async () => Promise.reject(new ApiError(410, 'gone'))) })
  wrap(<SignupPage api={api} onJoined={vi.fn()} />)

  expect(await screen.findByRole('heading', { name: 'Please start again.' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute('href', GOOGLE_SIGN_IN)
})
