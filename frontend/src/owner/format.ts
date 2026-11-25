import type { AuditEntry, PlayerPlan, PlayerStatus } from '../api/ownerTypes'
import { formatCredits } from '../pages/util'
import type { PillTone } from '../ui'

/** Microdollars per dollar and per coaching credit (backend CreditSettings). */
export const MICROUSD = 1_000_000
export const MICROUSD_PER_CREDIT = 10_000

/** Money for the owner: "$1,234.50", "-$3.20". */
export function dollars(microusd: number | null): string {
  if (microusd === null) return '–'
  const value = Math.abs(microusd) / MICROUSD
  const text = value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
  return microusd < 0 ? `-${text}` : text
}

/** Credits from microdollars, to one decimal when needed: "214.3", "34,000". */
export function credits(microusd: number): string {
  const value = Math.round((microusd / MICROUSD_PER_CREDIT) * 10) / 10
  return value.toLocaleString('en-US', { maximumFractionDigits: 1 })
}

export function percent(share: number | null): string {
  return share === null ? '–' : `${Math.round(share * 100)}%`
}

export function day(iso: string | null): string {
  if (!iso) return '–'
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** How long someone has waited: "today", "1 day", "22 days". */
export function waited(iso: string | null, now: number = Date.now()): string {
  if (!iso) return '–'
  const days = Math.floor((now - Date.parse(iso)) / 86_400_000)
  if (days <= 0) return 'today'
  return days === 1 ? '1 day' : `${days} days`
}

export const STATUS_LABEL: Record<PlayerStatus, string> = {
  waitlisted: 'Waitlisted',
  active: 'Active',
  suspended: 'Revoked',
}

/** Status pills: always with the word, never color alone. */
export const STATUS_TONE: Record<PlayerStatus, PillTone> = {
  active: 'analyzed',
  waitlisted: 'busy',
  suspended: 'blunder',
}

export const PLAN_LABEL: Record<PlayerPlan, string> = {
  subscriber: 'Subscriber',
  past_due: 'Past due',
  paid: 'Bought credits',
  trial: 'Trial only',
}

/** Coach tasks as the owner reads them; unknown ones show as stored. */
const TASK_LABEL: Record<string, string> = {
  chat: 'Chat',
  synopsis: 'Synopsis',
  explain: 'Explain',
  moment_intro: 'Moment intro',
  moment_feedback: 'Moment feedback',
  baseline_report: 'Baseline report',
  walkthrough: 'Walkthrough',
}

export function taskLabel(task: string): string {
  return TASK_LABEL[task] ?? task.replaceAll('_', ' ')
}

const LEDGER_LABEL: Record<string, string> = {
  trial: 'Free trial',
  allowance: 'Monthly allowance',
  top_up: 'Top-up',
  usage: 'Coaching',
  refund: 'Refund',
  expiry: 'Allowance expired',
  owner_grant: 'Added by owner',
  owner_removal: 'Removed by owner',
}

export function ledgerLabel(kind: string): string {
  return LEDGER_LABEL[kind] ?? kind
}

/** One line for an audit entry: what was done, with its reason or note. */
export function auditText(entry: AuditEntry): string {
  const d = entry.details
  switch (entry.action) {
    case 'accept':
      return 'Accepted from the waitlist'
    case 'suspend': {
      const parts = [`Access revoked: ${String(d.reason ?? '')}`]
      if (d.told_reason) parts.push('reason emailed')
      if (d.cancelled_subscription) parts.push('subscription cancelled')
      return parts.join(' · ')
    }
    case 'restore':
      return d.status === 'waitlisted' ? 'Restored (back on the waitlist)' : 'Access restored'
    case 'credits': {
      const amount = Number(d.credits ?? 0)
      const verb = amount >= 0 ? 'Added' : 'Removed'
      return `${verb} ${formatCredits(Math.abs(amount))} credits: ${String(d.note ?? '')}`
    }
    case 'metering':
      return d.unmetered ? 'Set to never be charged' : 'Charged for coaching again'
    case 'set_role':
      return `Role changed to ${String(d.to ?? '')}`
  }
}
