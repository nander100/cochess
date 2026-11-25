import { Route, Routes, useParams, useSearchParams } from 'react-router'
import type { OwnerApi, OwnerPeriod } from '../api/ownerTypes'
import { Eyebrow, Tabs } from '../ui'
import { OverviewPanel } from './OverviewPanel'
import { PERIODS, oneOf, playerFilters } from './params'
import { PlayerPage } from './PlayerPage'
import { PlayersPanel } from './PlayersPanel'
import { WaitlistPanel } from './WaitlistPanel'
import './owner.css'

type Tab = 'overview' | 'players' | 'waitlist'
const TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'players', label: 'Players' },
  { value: 'waitlist', label: 'Waitlist' },
] as const satisfies readonly { value: Tab; label: string }[]

/** The owner dashboard (SPEC_V4 §10) at /owner, only routed for an owner. Everything it shows
 * comes from /api/admin, which answers 404 to anyone else. */
export function OwnerArea({ api }: { api: OwnerApi }) {
  return (
    <div className="owner">
      <Routes>
        <Route index element={<OwnerHome api={api} />} />
        <Route path="players/:playerId" element={<PlayerRoute api={api} />} />
      </Routes>
    </div>
  )
}

function PlayerRoute({ api }: { api: OwnerApi }) {
  const { playerId = '' } = useParams()
  return <PlayerPage api={api} playerId={playerId} />
}

type Update = Record<string, string | number | boolean | undefined>

/** The tabs, with the tab, period, filters and page in the address bar (shareable, and kept on
 * reload and Back). */
function OwnerHome({ api }: { api: OwnerApi }) {
  const [params, setParams] = useSearchParams()
  const tab = oneOf<Tab>(params.get('tab'), ['overview', 'players', 'waitlist'], 'overview')
  const period = oneOf<OwnerPeriod>(params.get('period'), PERIODS.map((p) => p.value), '30d')
  const page = Math.max(1, Number(params.get('page')) || 1)

  /** Set these parameters on top of the current tab; a new tab starts with clean filters. */
  function go(update: Update) {
    const next = new URLSearchParams({ tab })
    for (const [key, value] of Object.entries(update)) {
      if (value !== undefined && value !== '' && value !== false) next.set(key, String(value))
    }
    if (next.get('page') === '1') next.delete('page')
    setParams(next)
  }

  return (
    <>
      <header className="owner-head">
        <Eyebrow>Owner</Eyebrow>
        <h1 className="owner-title">Dashboard</h1>
      </header>
      <Tabs label="Owner dashboard" tabs={TABS} value={tab} onChange={(value) => setParams({ tab: value })}>
        {tab === 'overview' && <OverviewPanel api={api} period={period} onPeriod={(next) => go({ period: next })} />}
        {tab === 'players' && (
          <PlayersPanel api={api} filters={playerFilters(params)} onFilters={(filters) => go({ ...filters })} />
        )}
        {tab === 'waitlist' && <WaitlistPanel api={api} page={page} onPage={(next) => go({ page: next })} />}
      </Tabs>
    </>
  )
}
