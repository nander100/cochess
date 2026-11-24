import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import type { ApiClient } from '../api/client'
import type { Billing, CreditEntry } from '../api/types'
import { Card, Skeleton } from '../ui'
import { formatCredits } from './util'

/** How often, and for how long, the page asks whether Stripe's webhook has landed. */
export const POLL_MS = 2000
export const POLL_TRIES = 30
/** A credit entry this recent counts as this payment's (the webhook may land before the page). */
const RECENT_MS = 15 * 60 * 1000

type Wait = { kind: 'waiting' } | { kind: 'arrived'; billing: Billing; entry: CreditEntry } | { kind: 'slow' }

/** After Stripe's checkout (SPEC_V4 §6.2). Credits only ever come from the verified webhook, so
 * this page waits for them to appear instead of trusting the redirect. */
export function BillingReturnPage({ api, now = Date.now }: { api: ApiClient; now?: () => number }) {
  const [params] = useSearchParams()
  const kind = params.get('product') === 'monthly' ? 'allowance' : 'top_up'
  const [wait, setWait] = useState<Wait>({ kind: 'waiting' })

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const since = now() - RECENT_MS
    const check = async (tries: number) => {
      const billing = await api.billing().catch(() => null)
      if (!live) return
      const entry = billing?.history.find((e) => e.kind === kind && Date.parse(e.created_at) >= since)
      if (billing && entry) setWait({ kind: 'arrived', billing, entry })
      else if (tries + 1 >= POLL_TRIES) setWait({ kind: 'slow' })
      else timer = setTimeout(() => void check(tries + 1), POLL_MS)
    }
    void check(0)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [api, kind, now])

  return (
    <Card as="section" className="profile-card" aria-labelledby="billing-return-title">
      <h1 id="billing-return-title" className="profile-card-title">
        Payment received
      </h1>
      {wait.kind === 'waiting' && (
        <>
          <p className="profile-intro">Thank you! Your credits will appear in a moment.</p>
          <Skeleton lines={1} label="Waiting for your credits…" />
        </>
      )}
      {wait.kind === 'arrived' && (
        <p className="profile-intro" role="status">
          {formatCredits(wait.entry.credits)} credits added. You now have {formatCredits(wait.billing.credits)}{' '}
          coaching credits.
        </p>
      )}
      {wait.kind === 'slow' && (
        <p className="profile-intro" role="status">
          Your payment went through, but your credits are taking longer than usual to arrive. They'll show on your
          profile as soon as Stripe confirms the payment; Stripe also emails you a receipt.
        </p>
      )}
      <p>
        <Link to="/profile#credits">See your credits</Link> or <Link to="/games">go to your games</Link>.
      </p>
    </Card>
  )
}
