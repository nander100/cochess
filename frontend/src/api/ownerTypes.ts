// The owner dashboard's API (SPEC_V4 §10), mirroring backend/app/admin/{overview,users,routes}.py.
// Money is in microdollars (1,000,000 = $1; 10,000 = one credit); times are ISO strings in UTC.

export type OwnerPeriod = '7d' | '30d' | 'month' | 'all'
export type PlayerStatus = 'waitlisted' | 'active' | 'suspended'
export type PlayerPlan = 'subscriber' | 'past_due' | 'paid' | 'trial'
export type PlayerStrength = 'standard' | 'deep'
export type PlayerSortKey = 'name' | 'joined' | 'last_active' | 'balance' | 'used' | 'cost' | 'games'
export type PlayerSort = PlayerSortKey | `-${PlayerSortKey}` | 'waited'

export interface OwnerOverview {
  period: OwnerPeriod
  since: string | null
  users: {
    total: number
    by_status: Partial<Record<PlayerStatus, number>>
    waitlist: number
    oldest_wait_since: string | null
  }
  plans: {
    subscribers: number
    past_due: number
    cancelled_this_month: number
    trial_with_credits: number
    trial_without_credits: number
    zero_credits: number
  }
  /** The last 7 and the last 30 days. */
  activity: {
    days: number
    sign_ups: number
    acceptances: number
    active_players: number
    games_added: number
    coach_calls: number
  }[]
  calls_by_task: Record<string, number>
  money: {
    /** As charged, including any tax, net of refunds, before Stripe fees. */
    revenue_microusd: number
    refunds_microusd: number
    api_cost_microusd: number
    difference_microusd: number
    coached_players: number
    coached_games: number
    cost_per_player_microusd: number | null
    cost_per_game_microusd: number | null
    credits_granted_microusd: number
    credits_spent_microusd: number
    cache_hit_rate: number | null
  }
  /** Daily; monthly (first of the month) for "all". */
  series: { day: string; revenue_microusd: number; api_cost_microusd: number }[]
}

export interface PlayerFilters {
  q?: string
  status?: PlayerStatus
  plan?: PlayerPlan
  strength?: PlayerStrength
  zero_credits?: boolean
  sort?: PlayerSort
  page?: number
}

export interface PlayerRow {
  id: string
  name: string
  email: string | null
  status: PlayerStatus
  plan: PlayerPlan
  coach_strength: PlayerStrength
  unmetered: boolean
  balance_microusd: number
  used_30d_microusd: number
  cost_30d_microusd: number
  games: number
  last_active_at: string | null
  joined_at: string
  waitlisted_at: string | null
}

export interface PlayerPage {
  rows: PlayerRow[]
  total: number
  page: number
  page_size: number
}

export interface AuditEntry {
  action: 'accept' | 'suspend' | 'restore' | 'credits' | 'metering' | 'set_role'
  /** The owner's name, or "CLI". */
  by: string
  details: Record<string, unknown>
  created_at: string
}

export interface LedgerLine {
  kind: string
  credits_microusd: number
  note: string | null
  created_at: string
  expires_at: string | null
}

export interface PlayerDetail {
  row: PlayerRow
  allowance_microusd: number
  lasting_microusd: number
  total_cost_microusd: number
  coach_calls: number
  subscription_status: string | null
  subscription_period_end: string | null
  billing_customer_id: string | null
  billing_dashboard_url: string | null
  admitted_at: string | null
  role: 'player' | 'owner'
  /** The last 12 weeks; `week` is the Monday. */
  cost_by_week: { week: string; by_task: Record<string, number> }[]
  ledger: LedgerLine[]
  audit: AuditEntry[]
}

export interface SuspendRequest {
  reason: string
  tell_reason: boolean
  cancel_subscription: boolean
}

export interface BulkAccepted {
  accepted: number
  /** Names (or ids) no longer on the waitlist. */
  skipped: string[]
}

/** The owner's API. Every call answers 404 to anyone who isn't the owner. */
export interface OwnerApi {
  overview(period: OwnerPeriod): Promise<OwnerOverview>
  players(filters: PlayerFilters): Promise<PlayerPage>
  player(id: string): Promise<PlayerDetail>
  accept(id: string): Promise<PlayerDetail>
  acceptMany(ids: string[]): Promise<BulkAccepted>
  suspend(id: string, body: SuspendRequest): Promise<PlayerDetail>
  restore(id: string): Promise<PlayerDetail>
  changeCredits(id: string, credits: number, note: string): Promise<PlayerDetail>
  setMetering(id: string, unmetered: boolean): Promise<PlayerDetail>
}
