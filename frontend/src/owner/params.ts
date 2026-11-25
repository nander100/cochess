import type {
  OwnerPeriod,
  PlayerFilters,
  PlayerPlan,
  PlayerSort,
  PlayerStatus,
  PlayerStrength,
} from '../api/ownerTypes'

/** The overview's periods, in the order the toggle shows them. */
export const PERIODS = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: 'month', label: 'This month' },
  { value: 'all', label: 'All time' },
] as const satisfies readonly { value: OwnerPeriod; label: string }[]

const STATUSES: readonly PlayerStatus[] = ['waitlisted', 'active', 'suspended']
const PLANS: readonly PlayerPlan[] = ['subscriber', 'past_due', 'paid', 'trial']
const STRENGTHS: readonly PlayerStrength[] = ['standard', 'deep']
const SORT_KEYS = ['name', 'joined', 'last_active', 'balance', 'used', 'cost', 'games'] as const

export function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}

/** The players tab's filters from the address bar; anything unknown is dropped. */
export function playerFilters(params: URLSearchParams): PlayerFilters {
  const sort = params.get('sort') ?? ''
  const pick = <T extends string>(name: string, allowed: readonly T[]) => {
    const value = params.get(name)
    return allowed.includes(value as T) ? (value as T) : undefined
  }
  return {
    q: params.get('q') || undefined,
    status: pick('status', STATUSES),
    plan: pick('plan', PLANS),
    strength: pick('strength', STRENGTHS),
    zero_credits: params.get('zero_credits') === 'true' || undefined,
    sort: SORT_KEYS.some((key) => sort === key || sort === `-${key}`) ? (sort as PlayerSort) : undefined,
    page: Math.max(1, Number(params.get('page')) || 1),
  }
}
