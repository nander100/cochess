import { DataActions } from '../account/DataActions'
import { useEffect } from 'react'
import { Link } from 'react-router'
import type { ApiClient } from '../api/client'
import type { Profile } from '../api/types'
import { Button, Pill } from '../ui'
import { AccountLayout } from './AccountLayout'

/** Starts Google sign-in (SPEC_V4 §4.1). A full page load, not a fetch: the browser leaves for
 * Google and comes back to the backend's callback. */
export const GOOGLE_SIGN_IN = '/api/auth/google/start?intent=signin'
export const GOOGLE_CONNECT = '/api/auth/google/start?intent=connect'
/** How often the waitlist page checks whether the player was accepted. */
export const WAITLIST_POLL_MS = 60_000

const SIGN_IN_PROBLEMS: Record<string, string> = {
  cancelled: 'Google sign-in was cancelled. Try again whenever you like.',
  expired: 'That took a little too long. Please try again.',
  failed: "We couldn't sign you in with Google. Please try again.",
  unverified: "Your Google account's email address isn't verified yet. Verify it with Google, then try again.",
  unavailable: "Signing in with Google isn't set up here yet. Ask the owner for a login link.",
  age: "Sorry, you can't create a CoChess account yet.",
}

/** Logged out: sign in with Google, which also joins the waitlist (SPEC_V4 §4.2). `reason` is
 * the callback's `?signin=` answer when something went wrong. */
export function SignInPage({ reason }: { reason: string | null }) {
  const problem = reason ? (SIGN_IN_PROBLEMS[reason] ?? SIGN_IN_PROBLEMS.failed) : null
  return (
    <AccountLayout>
      <div className="redeem-state">
        <span className="redeem-badge">Early access</span>
        <h1 className="redeem-title">Learn from every game you play.</h1>
        <p className="redeem-lead">
          Sign in with Google to join the waitlist, or to open CoChess if you've been accepted.
        </p>
        {problem && (
          <p className="redeem-note" role="alert">
            {problem}
          </p>
        )}
        {reason !== 'age' && (
          <a className="ui-button ui-button-primary redeem-go" href={GOOGLE_SIGN_IN}>
            Continue with Google
          </a>
        )}
        <p className="redeem-small">
          Got a login link from the owner? Open it in this browser instead.{' '}
          <Link to="/terms">Terms</Link> · <Link to="/privacy">Privacy</Link>
        </p>
      </div>
    </AccountLayout>
  )
}

interface AccountStatusPageProps {
  api: ApiClient
  profile: Profile
  /** The player was accepted (or restored) while this page was open. */
  onActive: (profile: Profile) => void
  onLogOut: () => void
  /** The account was deleted from this page (SPEC_V4 §11): the session has ended. */
  onDeleted: () => void
}

/** What a waitlisted or paused account sees instead of the app (SPEC_V4 §4.2, §4.4). The
 * waitlist page checks every minute and opens the app once the player is accepted. */
export function AccountStatusPage({ api, profile, onActive, onLogOut, onDeleted }: AccountStatusPageProps) {
  const waiting = profile.status === 'waitlisted'

  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => {
      api.me().then(
        (fresh) => {
          if (fresh.status === 'active') onActive(fresh)
        },
        () => undefined, // try again next time
      )
    }, WAITLIST_POLL_MS)
    return () => window.clearInterval(timer)
  }, [api, waiting, onActive])

  if (!waiting) {
    return (
      <AccountLayout>
        <div className="redeem-state" role="alert">
          <span className="redeem-badge">Access paused</span>
          <h1 className="redeem-title">Your access is paused.</h1>
          <p className="redeem-lead">
            Your games and history are kept. If you think this is a mistake, reply to the email we sent you.
            You can still download your data or delete your account.
          </p>
          <DataActions api={api.account} name={profile.name} onDeleted={onDeleted} />
          <Button variant="outline" onClick={onLogOut}>
            Sign out
          </Button>
        </div>
      </AccountLayout>
    )
  }
  const notice = profile.email
    ? `We'll email ${profile.email} as soon as your account is ready, and this page will open CoChess by itself.`
    : 'As soon as your account is ready, this page will open CoChess by itself.'
  return (
    <AccountLayout>
      <div className="redeem-state">
        <Pill tone="neutral">On the waitlist</Pill>
        <h1 className="redeem-title">You're on the list, {profile.name}.</h1>
        <p className="redeem-lead">We're letting players in a few at a time. {notice}</p>
        {profile.waitlisted_at && <p className="redeem-small">Joined {joinedOn(profile.waitlisted_at)}.</p>}
        <DataActions api={api.account} name={profile.name} onDeleted={onDeleted} />
        <Button variant="outline" onClick={onLogOut}>
          Sign out
        </Button>
      </div>
    </AccountLayout>
  )
}

function joinedOn(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
}

/** The terms and privacy policy. Their text is the owner's, reviewed by a lawyer (SPEC_V4 §15,
 * D6); until it's ready the pages say so. */
