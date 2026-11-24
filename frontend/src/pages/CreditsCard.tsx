import { useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'
import type { Billing, CoachStrength, CreditEntry } from '../api/types'
import { useSettings } from '../settings/settingsContext'
import { Card, SegmentedToggle, type ToggleOption } from '../ui'
import { formatCredits } from './util'

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
export function CreditsCard({ api }: { api: ApiClient }) {
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
