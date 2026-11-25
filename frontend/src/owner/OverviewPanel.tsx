import { Suspense, lazy } from 'react'
import type { OwnerApi, OwnerOverview, OwnerPeriod } from '../api/ownerTypes'
import { Card, ErrorState, SegmentedToggle, Skeleton } from '../ui'
import { credits, day, dollars, percent, taskLabel, waited } from './format'
import { PERIODS } from './params'
import { useLoad } from './useLoad'

const MoneyChart = lazy(() => import('./OwnerCharts').then((m) => ({ default: m.MoneyChart })))
const TaskChart = lazy(() => import('./OwnerCharts').then((m) => ({ default: m.TaskChart })))

interface OverviewPanelProps {
  api: OwnerApi
  period: OwnerPeriod
  onPeriod: (period: OwnerPeriod) => void
}

/** The overview (SPEC_V4 §10.1): money first, then players, paid vs unpaid and activity. */
export function OverviewPanel({ api, period, onPeriod }: OverviewPanelProps) {
  const { load, reload } = useLoad(() => api.overview(period), period)
  return (
    <div className="owner-overview">
      <div className="owner-toolbar">
        <SegmentedToggle legend="Period" hideLegend options={PERIODS} value={period} onChange={onPeriod} />
        {load.kind === 'ready' && (
          <p className="owner-quiet">
            {load.data.since ? `Since ${day(load.data.since)}` : 'All time'} · revenue as charged, net of
            refunds, before Stripe fees
          </p>
        )}
      </div>
      {load.kind === 'loading' && <Skeleton lines={6} label="Loading the overview…" />}
      {load.kind === 'error' && <ErrorState message={load.message} onRetry={reload} />}
      {load.kind === 'ready' && <Overview data={load.data} />}
    </div>
  )
}

function Overview({ data }: { data: OwnerOverview }) {
  const { money, users, plans } = data
  const share = money.revenue_microusd > 0 ? money.difference_microusd / money.revenue_microusd : null
  const byTask = Object.entries(data.calls_by_task).sort(([, a], [, b]) => b - a)
  return (
    <>
      <section className="owner-ledger" aria-label="Money">
        <Figure label="Revenue" value={dollars(money.revenue_microusd)} note={`${dollars(money.refunds_microusd)} refunded`} />
        <Figure
          label="API cost"
          value={dollars(money.api_cost_microusd)}
          note={`cache hit rate ${percent(money.cache_hit_rate)}`}
        />
        <Figure
          label="Difference"
          value={dollars(money.difference_microusd)}
          note={share === null ? 'no revenue yet' : `${percent(share)} of revenue`}
          loss={money.difference_microusd < 0}
        />
      </section>

      <div className="owner-grid">
        <Card as="section" className="owner-card owner-card-wide" aria-labelledby="owner-money-chart">
          <h2 id="owner-money-chart" className="owner-card-title">
            Revenue and API cost
          </h2>
          {data.series.length === 0 ? (
            <p className="owner-quiet">No payments or coach calls in this period.</p>
          ) : (
            <Suspense fallback={<Skeleton lines={4} label="Loading the chart…" />}>
              <MoneyChart overview={data} />
            </Suspense>
          )}
        </Card>

        <Card as="section" className="owner-card" aria-labelledby="owner-players">
          <h2 id="owner-players" className="owner-card-title">
            Players
          </h2>
          <Facts
            rows={[
              ['Total', users.total],
              ['Active', users.by_status.active ?? 0],
              ['Waitlisted', users.waitlist],
              ['Revoked', users.by_status.suspended ?? 0],
              ['Longest wait', waited(users.oldest_wait_since)],
            ]}
          />
        </Card>

        <Card as="section" className="owner-card" aria-labelledby="owner-plans">
          <h2 id="owner-plans" className="owner-card-title">
            Paid and unpaid
          </h2>
          <Facts
            rows={[
              ['Subscribers', plans.subscribers],
              ['Past due', plans.past_due],
              ['Cancelled this month', plans.cancelled_this_month],
              ['Trial only, credits left', plans.trial_with_credits],
              ['Trial only, none left', plans.trial_without_credits],
              ['At zero credits', plans.zero_credits],
            ]}
          />
        </Card>

        <Card as="section" className="owner-card" aria-labelledby="owner-units">
          <h2 id="owner-units" className="owner-card-title">
            Per player and game
          </h2>
          <Facts
            rows={[
              ['Players coached', money.coached_players],
              ['Cost per player', dollars(money.cost_per_player_microusd)],
              ['Games coached', money.coached_games],
              ['Cost per game', dollars(money.cost_per_game_microusd)],
              ['Credits granted', credits(money.credits_granted_microusd)],
              ['Credits spent', credits(money.credits_spent_microusd)],
            ]}
          />
        </Card>

        <Card as="section" className="owner-card owner-card-wide" aria-labelledby="owner-activity">
          <h2 id="owner-activity" className="owner-card-title">
            Activity
          </h2>
          <ActivityTable activity={data.activity} />
        </Card>

        <Card as="section" className="owner-card owner-card-wide" aria-labelledby="owner-tasks">
          <h2 id="owner-tasks" className="owner-card-title">
            Coach calls by task
          </h2>
          {byTask.length === 0 ? (
            <p className="owner-quiet">No coach calls in this period.</p>
          ) : (
            <div className="owner-split">
              <Facts rows={byTask.map(([task, count]) => [taskLabel(task), count] as const)} />
              <Suspense fallback={<Skeleton lines={3} label="Loading the chart…" />}>
                <TaskChart calls={data.calls_by_task} />
              </Suspense>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

export function Figure({ label, value, note, loss = false }: { label: string; value: string; note: string; loss?: boolean }) {
  return (
    <div className="owner-figure">
      <p className="owner-figure-label">{label}</p>
      <p className={loss ? 'owner-figure-value owner-loss' : 'owner-figure-value'}>{value}</p>
      <p className="owner-figure-note">{note}</p>
    </div>
  )
}

export function Facts({ rows }: { rows: readonly (readonly [string, string | number])[] }) {
  return (
    <dl className="owner-facts">
      {rows.map(([label, value]) => (
        <div key={label} className="owner-fact">
          <dt>{label}</dt>
          <dd>{typeof value === 'number' ? value.toLocaleString() : value}</dd>
        </div>
      ))}
    </dl>
  )
}

const ACTIVITY_ROWS = [
  ['Sign-ups', 'sign_ups'],
  ['Accepted', 'acceptances'],
  ['Active players', 'active_players'],
  ['Games added', 'games_added'],
  ['Coach calls', 'coach_calls'],
] as const

function ActivityTable({ activity }: { activity: OwnerOverview['activity'] }) {
  return (
    <table className="owner-mini-table">
      <thead>
        <tr>
          <th scope="col">
            <span className="visually-hidden">Measure</span>
          </th>
          {activity.map((window) => (
            <th key={window.days} scope="col">
              Last {window.days} days
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ACTIVITY_ROWS.map(([label, field]) => (
          <tr key={field}>
            <th scope="row">{label}</th>
            {activity.map((window) => (
              <td key={window.days}>{window[field].toLocaleString()}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
