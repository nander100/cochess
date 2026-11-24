import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { ApiClient } from '../api/client'
import type { Billing } from '../api/types'
import { formatCredits } from '../pages/util'
import './CreditsNotice.css'

interface CreditsNoticeProps {
  api: ApiClient
  /** A banner on the Games page, or a short note under the chat input (SPEC_V4 §5.3). */
  variant: 'banner' | 'note'
}

/** Says when coaching credits are running low or gone; shows nothing otherwise, while loading,
 * for unmetered accounts, or if the balance can't be read (the coach routes still refuse). */
export function CreditsNotice({ api, variant }: CreditsNoticeProps) {
  const [billing, setBilling] = useState<Billing | null>(null)

  useEffect(() => {
    let live = true
    api.billing().then(
      (loaded) => {
        if (live) setBilling(loaded)
      },
      () => undefined,
    )
    return () => {
      live = false
    }
  }, [api])

  if (billing === null || billing.unmetered || !(billing.low || billing.out)) return null
  const credits = Math.max(billing.credits, 0)
  const message = billing.out
    ? "You're out of coaching credits. Analysis still works; the coach is paused until you top up."
    : `You have ${formatCredits(credits)} coaching ${credits === 1 ? 'credit' : 'credits'} left.`
  return (
    <p className={`credits-notice credits-notice-${variant}`} role="status">
      {message} <Link to="/profile#credits">See your credits</Link>
    </p>
  )
}
