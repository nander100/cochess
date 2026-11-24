import { useEffect, useState } from 'react'
import { ApiError, type ApiClient } from '../api/client'
import type { Billing, BillingProduct, CoachStrength, CreditEntry, ProductKey } from '../api/types'
import { useSettings } from '../settings/settingsContext'
import { Button, Card, SegmentedToggle, type ToggleOption, useToast } from '../ui'
import { formatCredits } from './util'

/** Subscriptions in these states still bill (the backend refuses a second one). */
const LIVE_STATUSES = new Set(['active', 'trialing', 'past_due', 'incomplete'])

const STRENGTHS: ToggleOption<CoachStrength>[] = [
  { value: 'standard', label: 'Standard' },
  { value: 'deep', label: 'Deep' },
]

const KINDS: Record<CreditEntry['kind'], string> = {
  trial: 'Free trial',
  allowance: 'Monthly allowance',
  top_up: 'Top-up',
  usage: 'Coaching',
  refund: 'Refund',
  expiry: 'Unused allowance expired',
  owner_grant: 'Added by CoChess',
  owner_removal: 'Removed by CoChess',
}

/** Coaching credits and coach strength (SPEC_V4 §5, §7). Credits pay for the coach only; the
 * engine runs in the browser and costs nothing. */
export function CreditsCard({
  api,
  redirect = (url) => window.location.assign(url),
}: {
  api: ApiClient
  /** Where checkout and the portal take the browser (tests watch it). */
  redirect?: (url: string) => void
}) {
  const { settings, update } = useSettings()
  const [billing, setBilling] = useState<Billing | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    api.billing().then(setBilling, () => setFailed(true))
  }, [api])

  const strength = settings.coach_strength
  return (
    <Card as="section" className="profile-card" aria-labelledby="profile-credits" id="credits">
      <h2 id="profile-credits" className="profile-card-title">
        Coaching credits
      </h2>
      {failed && <p className="ui-field-error">Your credits couldn't be loaded. Try again later.</p>}
      {billing && <p className="profile-intro">{balanceText(billing, strength)}</p>}
      <SegmentedToggle
        legend="Coach strength"
        options={STRENGTHS}
        value={strength}
        onChange={(coach_strength) => update({ coach_strength })}
        describedBy="coach-strength-help"
      />
      <p id="coach-strength-help" className="profile-intro">
        {strengthText(billing)} It applies to new coaching from now on.
      </p>
      {billing && billing.payments_enabled && !billing.unmetered && (
        <Plans api={api} billing={billing} redirect={redirect} />
      )}
      {billing && billing.history.length > 0 && (
        <ul className="profile-credits-history" aria-label="Recent credit changes">
          {billing.history.slice(0, 5).map((entry, i) => (
            <li key={`${entry.created_at}-${i}`}>
              <span>
                {KINDS[entry.kind]}
                {entry.note ? `: ${entry.note}` : ''}
              </span>
              <span>
                {entry.credits > 0 ? '+' : ''}
                {formatCredits(entry.credits)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function balanceText(billing: Billing, strength: CoachStrength): string {
  if (billing.unmetered) return 'Your coaching is never charged on this account.'
  const left = `${formatCredits(billing.credits)} credits left`
  const perGame = billing.credits_per_game[strength]
  const games =
    billing.credits > 0 && perGame > 0
      ? `, about ${Math.floor(billing.credits / perGame)} games at ${strength === 'deep' ? 'Deep' : 'Standard'}`
      : ''
  return `${left}${games}. Credits pay for the coach; analyzing games is free.`
}

function strengthText(billing: Billing | null): string {
  if (billing === null) return 'Deep uses a stronger coach, so your credits go faster.'
  const { standard, deep } = billing.credits_per_game
  return (
    `Standard: about ${formatCredits(standard)} credits a game. Deep: a stronger coach for your ` +
    `reviews and questions, about ${formatCredits(deep)} credits a game, so credits go about ` +
    `${formatCredits(Math.round((deep / standard) * 10) / 10)} times faster.`
  )
}

/** Subscribe, top up, or manage the subscription (SPEC_V4 §6.2): each opens Stripe's own page, so
 * card details never reach CoChess. Prices are shown before tax; Stripe adds any tax. */
function Plans({ api, billing, redirect }: { api: ApiClient; billing: Billing; redirect: (url: string) => void }) {
  const { show } = useToast()
  const [busy, setBusy] = useState(false)
  const subscribed = billing.subscription !== null && LIVE_STATUSES.has(billing.subscription.status)
  const status = subscriptionText(billing)

  async function go(open: () => Promise<{ url: string }>) {
    setBusy(true)
    try {
      redirect((await open()).url)
    } catch (error) {
      show(error instanceof ApiError ? error.message : "The payment page couldn't be opened. Try again.", 'error')
      setBusy(false)
    }
  }

  const buy = (key: ProductKey) => () => void go(() => api.checkout(key))
  return (
    <div className="profile-plans">
      {status && <p className="profile-intro">{status}</p>}
      <div className="profile-plans-actions">
        {billing.products.map((product) =>
          product.recurring && subscribed ? null : (
            <Button
              key={product.key}
              variant={product.recurring ? 'primary' : 'outline'}
              disabled={busy}
              onClick={buy(product.key)}
            >
              {productLabel(product)}
            </Button>
          ),
        )}
        {billing.has_billing_account && (
          <Button variant="link" disabled={busy} onClick={() => void go(() => api.billingPortal())}>
            {subscribed ? 'Manage subscription' : 'Receipts and payments'}
          </Button>
        )}
      </div>
      <p className="profile-intro">
        Prices are before tax; Stripe, which sells for CoChess, adds any tax at checkout.
        {billing.needs_guardian && ' Players under 18 need a parent or guardian to pay.'}
      </p>
    </div>
  )
}

function productLabel(product: BillingProduct): string {
  const dollars = product.price_cents / 100
  const price = `$${Number.isInteger(dollars) ? dollars : dollars.toFixed(2)}`
  return product.recurring
    ? `Subscribe: ${price} a month for ${product.credits} credits`
    : `Buy ${product.credits} credits for ${price}`
}

function subscriptionText(billing: Billing): string | null {
  const sub = billing.subscription
  if (sub === null) return null
  const until = sub.period_end ? new Date(sub.period_end).toLocaleDateString() : null
  switch (sub.status) {
    case 'active':
    case 'trialing':
      return until ? `Your subscription renews on ${until}.` : 'Your subscription is active.'
    case 'past_due':
    case 'incomplete':
      return "Your last payment didn't go through. Update your card to get this month's credits."
    default:
      return 'Your subscription has ended. Your top-up credits are still yours.'
  }
}
