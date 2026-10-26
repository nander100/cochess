import { useEffect, useRef, useState } from 'react'
import type { ApiClient } from '../api/client'
import { errorText } from './util'

interface RedeemPageProps {
  api: ApiClient
  /** The token from the link: `/redeem#token=…` (a fragment never reaches server logs). */
  token: string | null
  onRedeemed: () => void
}

/** Opening a one-time login link (SPEC_V2 §4.1). */
export function RedeemPage({ api, token, onRedeemed }: RedeemPageProps) {
  const [error, setError] = useState<string | null>(null)
  // An invite works once, and StrictMode runs effects twice in development: redeem only once.
  const started = useRef(false)

  useEffect(() => {
    if (started.current || token === null) return
    started.current = true
    api.redeem(token).then(onRedeemed, (caught: unknown) => setError(errorText(caught)))
  }, [api, token, onRedeemed])

  if (token === null) {
    return (
      <p className="run-error" role="alert">
        This login link is incomplete. Copy the whole link you were sent.
      </p>
    )
  }
  if (error) {
    return (
      <p className="run-error" role="alert">
        {error}
      </p>
    )
  }
  return <p className="coach-writing">Logging you in…</p>
}
