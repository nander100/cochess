import type { OwnerApi, OwnerOverview, PlayerDetail, PlayerPage, PlayerRow } from '../api/ownerTypes'

// Made-up owner-dashboard data for tests (SPEC_V4 §10). Money in microdollars.

export const OVERVIEW: OwnerOverview = {
  period: '30d',
  since: '2026-10-25T12:00:00Z',
  users: {
    total: 42,
    by_status: { active: 30, waitlisted: 9, suspended: 3 },
    waitlist: 9,
    oldest_wait_since: '2026-11-02T08:00:00Z',
  },
  plans: {
    subscribers: 12,
    past_due: 1,
    cancelled_this_month: 2,
    trial_with_credits: 10,
    trial_without_credits: 4,
    zero_credits: 6,
  },
  activity: [
    { days: 7, sign_ups: 5, acceptances: 3, active_players: 18, games_added: 64, coach_calls: 410 },
    { days: 30, sign_ups: 17, acceptances: 11, active_players: 27, games_added: 240, coach_calls: 1600 },
  ],
  calls_by_task: { chat: 900, synopsis: 240, moment_intro: 200, walkthrough: 60 },
  money: {
    revenue_microusd: 132_500_000,
    refunds_microusd: 5_000_000,
    api_cost_microusd: 41_250_000,
    difference_microusd: 91_250_000,
    coached_players: 25,
    coached_games: 230,
    cost_per_player_microusd: 1_650_000,
    cost_per_game_microusd: 179_347,
    credits_granted_microusd: 52_000_000,
    credits_spent_microusd: 41_250_000,
    cache_hit_rate: 0.62,
  },
  series: [
    { day: '2026-11-20', revenue_microusd: 10_000_000, api_cost_microusd: 1_500_000 },
    { day: '2026-11-21', revenue_microusd: 0, api_cost_microusd: 2_100_000 },
  ],
}

export const PLAYER_ROW: PlayerRow = {
  id: 'p-ana',
  name: 'Ana Rivera',
  email: 'ana@example.com',
  status: 'active',
  plan: 'subscriber',
  coach_strength: 'standard',
  unmetered: false,
  balance_microusd: 2_143_000,
  used_30d_microusd: 1_200_000,
  cost_30d_microusd: 1_180_000,
  games: 14,
  last_active_at: '2026-11-23T18:00:00Z',
  joined_at: '2026-10-02T09:00:00Z',
  waitlisted_at: null,
}

export const WAITING_ROW: PlayerRow = {
  ...PLAYER_ROW,
  id: 'p-ben',
  name: 'Ben Okafor',
  email: 'ben@example.com',
  status: 'waitlisted',
  plan: 'trial',
  balance_microusd: 0,
  used_30d_microusd: 0,
  cost_30d_microusd: 0,
  games: 0,
  last_active_at: null,
  joined_at: '2026-11-02T08:00:00Z',
  waitlisted_at: '2026-11-02T08:00:00Z',
}

export const PLAYERS: PlayerPage = { rows: [PLAYER_ROW], total: 1, page: 1, page_size: 50 }

export const PLAYER_DETAIL: PlayerDetail = {
  row: PLAYER_ROW,
  allowance_microusd: 1_643_000,
  lasting_microusd: 500_000,
  total_cost_microusd: 3_400_000,
  coach_calls: 380,
  subscription_status: 'active',
  subscription_period_end: '2026-12-02T09:00:00Z',
  billing_customer_id: 'cus_test_ana',
  billing_dashboard_url: 'https://dashboard.stripe.com/test/customers/cus_test_ana',
  admitted_at: '2026-10-02T09:00:00Z',
  role: 'player',
  cost_by_week: [
    { week: '2026-11-09', by_task: { chat: 400_000, synopsis: 120_000 } },
    { week: '2026-11-16', by_task: { chat: 520_000, walkthrough: 90_000 } },
  ],
  ledger: [
    { kind: 'owner_grant', credits_microusd: 500_000, note: 'Beta tester', created_at: '2026-11-20T10:00:00Z', expires_at: null },
    { kind: 'allowance', credits_microusd: 3_000_000, note: null, created_at: '2026-11-02T09:00:00Z', expires_at: '2026-12-02T09:00:00Z' },
  ],
  audit: [
    { action: 'credits', by: 'Owner', details: { credits: 50, note: 'Beta tester' }, created_at: '2026-11-20T10:00:00Z' },
    { action: 'accept', by: 'CLI', details: {}, created_at: '2026-10-02T09:00:00Z' },
  ],
}

export function fakeOwnerApi(overrides: Partial<OwnerApi> = {}): OwnerApi {
  return {
    overview: vi.fn(async (period) => ({ ...OVERVIEW, period })),
    players: vi.fn(async () => PLAYERS),
    player: vi.fn(async () => PLAYER_DETAIL),
    accept: vi.fn(async () => ({ ...PLAYER_DETAIL, row: { ...WAITING_ROW, status: 'active' as const } })),
    acceptMany: vi.fn(async (ids: string[]) => ({ accepted: ids.length, skipped: [] })),
    suspend: vi.fn(async () => ({ ...PLAYER_DETAIL, row: { ...PLAYER_ROW, status: 'suspended' as const } })),
    restore: vi.fn(async () => PLAYER_DETAIL),
    changeCredits: vi.fn(async () => PLAYER_DETAIL),
    setMetering: vi.fn(async (_id: string, unmetered: boolean) => ({
      ...PLAYER_DETAIL,
      row: { ...PLAYER_ROW, unmetered },
    })),
    ...overrides,
  }
}
