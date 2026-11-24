import { type FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError, type ApiClient } from '../api/client'
import type { SignupInfo } from '../api/types'
import { Button, Input, Skeleton } from '../ui'
import { AccountLayout } from './AccountLayout'
import { GOOGLE_SIGN_IN } from './AccountPages'
import { errorText } from './util'

interface SignupPageProps {
  api: ApiClient
  /** Signed up: the account is on the waitlist and signed in. */
  onJoined: () => void
}

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; info: SignupInfo }
  | { kind: 'gone' }
  | { kind: 'too-young' }
  | { kind: 'error'; message: string }

const YEAR = /^\d{4}$/

/** A new Google account's last step before the waitlist (SPEC_V4 §4.2, §11): the age check and
 * the terms. The age question is neutral (no hint of the cutoff, no "I'm old enough" box), as
 * the FTC advises; only an age band is kept. */
export function SignupPage({ api, onJoined }: SignupPageProps) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    api.signupInfo().then(
      (info) => setState({ kind: 'ready', info }),
      (caught: unknown) =>
        setState(
          caught instanceof ApiError && caught.status === 410
            ? { kind: 'gone' }
            : { kind: 'error', message: errorText(caught) },
        ),
    )
  }, [api])

  return (
    <AccountLayout>
      {state.kind === 'loading' && <Skeleton label="Loading…" />}
      {state.kind === 'ready' && (
        <SignupForm api={api} info={state.info} onJoined={onJoined} onEnded={(end) => setState({ kind: end })} />
      )}
      {state.kind === 'gone' && (
        <div className="redeem-state" role="alert">
          <h1 className="redeem-title">Please start again.</h1>
          <p className="redeem-lead">Your sign-up took a little too long, so we didn't keep it.</p>
          <a className="ui-button ui-button-primary redeem-go" href={GOOGLE_SIGN_IN}>
            Continue with Google
          </a>
        </div>
      )}
      {state.kind === 'too-young' && (
        <div className="redeem-state" role="alert">
          <h1 className="redeem-title">Sorry, you can't create a CoChess account yet.</h1>
          <p className="redeem-lead">We haven't kept anything you entered.</p>
        </div>
      )}
      {state.kind === 'error' && (
        <div className="redeem-state" role="alert">
          <h1 className="redeem-title-small">Something went wrong.</h1>
          <p className="redeem-lead">{state.message}</p>
          <a className="ui-button ui-button-primary redeem-go" href={GOOGLE_SIGN_IN}>
            Try again
          </a>
        </div>
      )}
    </AccountLayout>
  )
}

interface SignupFormProps {
  api: ApiClient
  info: SignupInfo
  onJoined: () => void
  onEnded: (end: 'gone' | 'too-young') => void
}

function SignupForm({ api, info, onJoined, onEnded }: SignupFormProps) {
  const [year, setYear] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!YEAR.test(year.trim())) {
      setProblem('Enter the year as four digits, like 1990.')
      return
    }
    if (!agreed) {
      setProblem('Please agree to the terms and privacy policy to continue.')
      return
    }
    setBusy(true)
    setProblem(null)
    try {
      await api.signUp({ birth_year: Number(year.trim()), accept_terms: true, terms_version: info.terms_version })
      onJoined()
    } catch (caught: unknown) {
      setBusy(false)
      if (caught instanceof ApiError && caught.status === 403) onEnded('too-young')
      else if (caught instanceof ApiError && caught.status === 410) onEnded('gone')
      else setProblem(errorText(caught))
    }
  }

  return (
    <form className="redeem-state" onSubmit={(e) => void handleSubmit(e)} noValidate aria-labelledby="signup-title">
      <span className="redeem-badge">Join the waitlist</span>
      <h1 id="signup-title" className="redeem-title">
        Welcome, {info.name}.
      </h1>
      <p className="redeem-lead">You're signing up as {info.email}. Two quick things, then you're on the waitlist.</p>
      <Input
        label="What year were you born?"
        inputMode="numeric"
        autoComplete="bday-year"
        maxLength={4}
        value={year}
        onChange={(e) => setYear(e.target.value)}
      />
      <label className="signup-consent">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        <span>
          I agree to the{' '}
          <Link to="/terms" target="_blank" rel="noreferrer">
            Terms of Service
          </Link>{' '}
          and the{' '}
          <Link to="/privacy" target="_blank" rel="noreferrer">
            Privacy Policy
          </Link>
          . If I'm under 18, a parent or guardian agrees too.
        </span>
      </label>
      {problem && (
        <p className="ui-field-error" role="alert">
          {problem}
        </p>
      )}
      <Button type="submit" disabled={busy} className="redeem-go">
        {busy ? 'Joining…' : 'Join the waitlist'}
      </Button>
    </form>
  )
}
