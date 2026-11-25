import { Suspense, lazy } from 'react'
import { Link } from 'react-router'
import type { OwnerApi, PlayerDetail } from '../api/ownerTypes'
import { Card, ErrorState, Pill, Skeleton, Table } from '../ui'
import { PLAN_LABEL, STATUS_LABEL, STATUS_TONE, auditText, credits, dateTime, day, dollars, ledgerLabel } from './format'
import { Facts, Figure } from './OverviewPanel'
import { PlayerActions } from './PlayerActions'
import { useLoad } from './useLoad'

/** The server sends this many ledger entries, newest first. */
const LEDGER_SHOWN = 100

const WeeklyCostChart = lazy(() => import('./OwnerCharts').then((m) => ({ default: m.WeeklyCostChart })))

/** One player (SPEC_V4 §10.2): their numbers, cost per task, credit ledger, subscription and the
 * audit log of owner actions, with the actions. Never the content of their games or chats. */
export function PlayerPage({ api, playerId }: { api: OwnerApi; playerId: string }) {
  const { load, reload, replace } = useLoad(() => api.player(playerId), playerId)
  return (
    <div className="owner-player">
      <Link to="/owner?tab=players" className="owner-back">
        ← All players
      </Link>
      {load.kind === 'loading' && <Skeleton lines={8} label="Loading the player…" />}
      {load.kind === 'error' && <ErrorState message={load.message} onRetry={reload} />}
      {load.kind === 'ready' && <Player api={api} detail={load.data} onChanged={replace} />}
    </div>
  )
}

interface PlayerProps {
  api: OwnerApi
  detail: PlayerDetail
  onChanged: (detail: PlayerDetail) => void
}

function Player({ api, detail, onChanged }: PlayerProps) {
  const { row } = detail
  return (
    <>
      <header className="owner-player-head">
        <div>
          <h1 className="owner-title">{row.name}</h1>
          <p className="owner-quiet">
            {row.email ?? 'no email'} · joined {day(row.joined_at)}
            {detail.role === 'owner' && ' · owner'}
          </p>
          <div className="owner-pills">
            <Pill tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Pill>
            <Pill>{PLAN_LABEL[row.plan]}</Pill>
            {row.unmetered && <Pill tone="plan">Never charged</Pill>}
            {row.coach_strength === 'deep' && <Pill>Deep coach</Pill>}
          </div>
        </div>
        <PlayerActions api={api} detail={detail} onChanged={onChanged} />
      </header>

      <section className="owner-ledger" aria-label="Numbers">
        <Figure
          label="Balance"
          value={`${credits(row.balance_microusd)} credits`}
          note={`${credits(detail.allowance_microusd)} allowance · ${credits(detail.lasting_microusd)} lasting`}
          loss={row.balance_microusd < 0}
        />
        <Figure
          label="API cost, 30 days"
          value={dollars(row.cost_30d_microusd)}
          note={`${credits(row.used_30d_microusd)} credits used`}
        />
        <Figure
          label="API cost, ever"
          value={dollars(detail.total_cost_microusd)}
          note={`${detail.coach_calls.toLocaleString()} coach calls · ${row.games.toLocaleString()} games`}
        />
      </section>

      <div className="owner-grid">
        <Card as="section" className="owner-card owner-card-wide" aria-labelledby="owner-weekly">
          <h2 id="owner-weekly" className="owner-card-title">
            API cost per week, by task
          </h2>
          {detail.cost_by_week.length === 0 ? (
            <p className="owner-quiet">No coach calls in the last 12 weeks.</p>
          ) : (
            <Suspense fallback={<Skeleton lines={4} label="Loading the chart…" />}>
              <WeeklyCostChart weeks={detail.cost_by_week} />
            </Suspense>
          )}
        </Card>

        <Card as="section" className="owner-card" aria-labelledby="owner-subscription">
          <h2 id="owner-subscription" className="owner-card-title">
            Subscription
          </h2>
          <Facts
            rows={[
              ['Status', detail.subscription_status ?? 'none'],
              ['Period ends', day(detail.subscription_period_end)],
              ['Last active', day(row.last_active_at)],
              ['Accepted', day(detail.admitted_at)],
            ]}
          />
          {detail.billing_dashboard_url && (
            <a className="owner-external" href={detail.billing_dashboard_url} target="_blank" rel="noreferrer noopener">
              Open the customer in Stripe
            </a>
          )}
        </Card>

        <Card as="section" className="owner-card owner-card-double" aria-labelledby="owner-audit">
          <h2 id="owner-audit" className="owner-card-title">
            Owner actions
          </h2>
          {detail.audit.length === 0 ? (
            <p className="owner-quiet">No owner actions on this player yet.</p>
          ) : (
            <ol className="owner-audit" aria-label="Audit log">
              {detail.audit.map((entry, index) => (
                <li key={`${entry.created_at}-${index}`}>
                  <span className="owner-audit-what">{auditText(entry)}</span>
                  <span className="owner-sub">
                    {dateTime(entry.created_at)} · by {entry.by}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <Card as="section" className="owner-card owner-card-wide" aria-labelledby="owner-ledger">
          <h2 id="owner-ledger" className="owner-card-title">
            Credit ledger
          </h2>
          {detail.ledger.length === 0 ? (
            <p className="owner-quiet">No credit changes yet.</p>
          ) : (
            <>
              {detail.ledger.length >= LEDGER_SHOWN && (
                <p className="owner-quiet">The latest {LEDGER_SHOWN} changes.</p>
              )}
              <LedgerTable ledger={detail.ledger} />
            </>
          )}
        </Card>
      </div>
    </>
  )
}

function LedgerTable({ ledger }: { ledger: PlayerDetail['ledger'] }) {
  return (
    <Table className="owner-table" aria-labelledby="owner-ledger">
      <thead>
        <tr>
          <th scope="col">When</th>
          <th scope="col">What</th>
          <th scope="col" className="owner-num">
            Credits
          </th>
          <th scope="col">Note</th>
        </tr>
      </thead>
      <tbody>
        {ledger.map((line, index) => (
          <tr key={`${line.created_at}-${index}`}>
            <td>{dateTime(line.created_at)}</td>
            <td>
              {ledgerLabel(line.kind)}
              {line.expires_at && <span className="owner-sub">expires {day(line.expires_at)}</span>}
            </td>
            <td className={line.credits_microusd < 0 ? 'owner-num owner-loss' : 'owner-num'}>
              {line.credits_microusd > 0 ? '+' : ''}
              {credits(line.credits_microusd)}
            </td>
            <td>{line.note ?? ''}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  )
}
