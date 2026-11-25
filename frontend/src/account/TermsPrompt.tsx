import { useState } from 'react'
import { Link } from 'react-router'
import type { AccountApi } from '../api/accountTypes'
import type { Profile } from '../api/types'
import { AccountLayout } from '../pages/AccountLayout'
import { errorText } from '../pages/util'
import { Button } from '../ui'
import './account.css'

interface TermsPromptProps {
  api: AccountApi
  profile: Profile
  /** Accepted: the app reloads the profile and carries on. */
  onAccepted: () => void
  onLogOut: () => void
}

/** A new terms version asks every signed-in account to accept it before continuing (SPEC_V4 §11).
 * The terms and privacy pages open in a new tab so this one keeps its place. */
export function TermsPrompt({ api, profile, onAccepted, onLogOut }: TermsPromptProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const guardian = profile.age_band === '13_17'

  async function accept() {
    setBusy(true)
    setError(null)
    try {
      await api.acceptTerms(profile.terms_version)
      onAccepted()
    } catch (failure) {
      setError(errorText(failure))
      setBusy(false)
    }
  }

  return (
    <AccountLayout>
      <div className="redeem-state">
        <span className="redeem-badge">Updated terms</span>
        <h1 className="redeem-title">We've updated our terms, {profile.name}.</h1>
        <p className="redeem-lead">
          Please read the{' '}
          <Link to="/terms" target="_blank">
            Terms of Service
          </Link>{' '}
          and the{' '}
          <Link to="/privacy" target="_blank">
            Privacy Policy
          </Link>{' '}
          before you continue.
        </p>
        {guardian && <p className="redeem-lead">A parent or guardian needs to agree to the terms for you.</p>}
        {error && (
          <p className="terms-error" role="alert">
            {error}
          </p>
        )}
        <div className="terms-actions">
          <Button disabled={busy} onClick={() => void accept()}>
            {busy ? 'Saving…' : 'I agree'}
          </Button>
          <Button variant="outline" disabled={busy} onClick={onLogOut}>
            Sign out
          </Button>
        </div>
      </div>
    </AccountLayout>
  )
}
