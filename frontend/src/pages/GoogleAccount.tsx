import { useSearchParams } from 'react-router'
import type { Profile } from '../api/types'
import { Card, Pill } from '../ui'
import { GOOGLE_CONNECT } from './AccountPages'

const ANSWERS: Record<string, { tone: 'good' | 'problem'; text: string }> = {
  connected: { tone: 'good', text: 'Google is connected. Next time, sign in with Google.' },
  taken: { tone: 'problem', text: 'That Google account already belongs to another CoChess player.' },
  already: { tone: 'problem', text: 'This account is already connected to a different Google account.' },
  failed: { tone: 'problem', text: "We couldn't connect Google. Please try again." },
}

/** Signing in with Google (SPEC_V4 §4.5): players who joined by invite link connect their Google
 * account here, then sign in with it. Accounts are never matched by email. `?google=` is the
 * callback's answer. */
export function GoogleAccount({ profile }: { profile: Profile }) {
  const [params] = useSearchParams()
  const answer = ANSWERS[params.get('google') ?? '']
  return (
    <Card as="section" className="profile-card" aria-labelledby="profile-google">
      <h2 id="profile-google" className="profile-card-title">
        Signing in
      </h2>
      {profile.google_connected ? (
        <p className="profile-intro">
          <Pill tone="analyzed">Google connected</Pill> You sign in with Google
          {profile.email ? ` as ${profile.email}` : ''}.
        </p>
      ) : (
        <>
          <p className="profile-intro">
            Connect your Google account to sign in with it instead of a login link. Your games and history stay as
            they are.
          </p>
          <a className="ui-button ui-button-primary profile-google-connect" href={GOOGLE_CONNECT}>
            Connect Google
          </a>
        </>
      )}
      {answer && (
        <p className={answer.tone === 'good' ? 'profile-intro' : 'ui-field-error'} role="status">
          {answer.text}
        </p>
      )}
    </Card>
  )
}
