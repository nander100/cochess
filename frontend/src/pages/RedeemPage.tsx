import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import type { ApiClient } from '../api/client'
import type { Profile } from '../api/types'
import { useTheme } from '../theme/themeContext'
import { Button, Pill, ProgressBar } from '../ui'
import './RedeemPage.css'
import { errorText } from './util'

interface RedeemPageProps {
  api: ApiClient
  /** The token from the link: `/redeem#token=…` (a fragment never reaches server logs). */
  token: string | null
  /** A used link opened again in a browser that is already logged in: just go in. */
  onRedeemed: () => void
}

type State = { kind: 'checking' } | { kind: 'accepted'; profile: Profile | null } | { kind: 'invalid'; message: string }

const STEPS = ['Your profile: name, Elo, time control', '12-game assessment (optional)', 'Your baseline report']

/** Opening a one-time login link (SPEC_V2 §4.1), as in Redeem.dc.html: checking, accepted, or
 * not valid. */
export function RedeemPage({ api, token, onRedeemed }: RedeemPageProps) {
  const [state, setState] = useState<State>(
    token === null
      ? { kind: 'invalid', message: 'This login link is incomplete. Copy the whole link you were sent.' }
      : { kind: 'checking' },
  )
  // An invite works once, and StrictMode runs effects twice in development: redeem only once.
  const started = useRef(false)

  useEffect(() => {
    if (started.current || token === null) return
    started.current = true
    api.redeem(token).then(
      () => api.me().then(
        (profile) => setState({ kind: 'accepted', profile }),
        () => setState({ kind: 'accepted', profile: null }),
      ),
      (caught: unknown) => {
        api.me().then(onRedeemed, () => setState({ kind: 'invalid', message: errorText(caught) }))
      },
    )
  }, [api, token, onRedeemed])

  return (
    <div className="redeem">
      <section className="redeem-brand" aria-hidden="true">
        <div className="redeem-logo">
          <span className="redeem-logo-tile">♞︎</span>
          <span className="redeem-wordmark">CoChess</span>
        </div>
        <div className="redeem-tiles">
          {Array.from({ length: 16 }, (_, i) => (
            <span key={i} className={(Math.floor(i / 4) + i) % 2 === 0 ? 'light' : 'dark'} />
          ))}
        </div>
        <p className="redeem-tagline">The engine finds the moves. Your coach explains them.</p>
      </section>
      <main className="redeem-main">
        <div className="redeem-card">
          {state.kind === 'checking' && (
            <>
              <h1 className="redeem-title-small">Checking your invite…</h1>
              <ProgressBar label="Checking invite" done={2} total={5} />
            </>
          )}
          {state.kind === 'accepted' && <Accepted profile={state.profile} />}
          {state.kind === 'invalid' && (
            <div className="redeem-state" role="alert">
              <span className="redeem-badge">Link not valid</span>
              <h1 className="redeem-title">This invite link can't be used.</h1>
              <p className="redeem-lead">{state.message}</p>
              <p className="redeem-lead">
                Ask the owner to send you a new one. Your games and progress are kept.
              </p>
              <div className="redeem-note">Already signed in on another device? Open CoChess there instead.</div>
            </div>
          )}
          <ThemeButton />
        </div>
      </main>
    </div>
  )
}

function Accepted({ profile }: { profile: Profile | null }) {
  const ready = profile?.complete ?? false
  return (
    <div className="redeem-state">
      <Pill tone="analyzed">Invite accepted</Pill>
      <h1 className="redeem-title">{profile ? `Welcome, ${profile.name}.` : 'Welcome.'}</h1>
      <p className="redeem-lead">
        You're signed in on this device.{' '}
        {ready
          ? 'Your games and coach are waiting.'
          : 'Next, tell your coach a little about your chess so explanations fit your level.'}
      </p>
      {!ready && (
        <ol className="redeem-steps">
          {STEPS.map((label, i) => (
            <li key={label} className={i === 0 ? 'now' : 'later'}>
              <span className="redeem-step-number" aria-hidden="true">
                {i + 1}
              </span>
              {label}
            </li>
          ))}
        </ol>
      )}
      <Link className="ui-button ui-button-primary redeem-go" to={ready ? '/games' : '/profile'}>
        {ready ? 'Open my games' : 'Set up my profile'}
      </Link>
      <p className="redeem-small">
        Invite links work once and expire after 7 days. If you sign out or switch devices, ask the
        owner for a new link.
      </p>
    </div>
  )
}

function ThemeButton() {
  const { theme, toggle } = useTheme()
  return (
    <Button variant="outline" className="redeem-theme" onClick={toggle}>
      {theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </Button>
  )
}
