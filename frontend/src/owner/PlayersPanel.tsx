import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import { playerQuery } from '../api/client'
import type {
  OwnerApi,
  PlayerFilters,
  PlayerPlan,
  PlayerRow,
  PlayerSort,
  PlayerSortKey,
  PlayerStatus,
  PlayerStrength,
} from '../api/ownerTypes'
import { Button, EmptyState, ErrorState, Input, Pill, Select, Skeleton, Table } from '../ui'
import { PLAN_LABEL, STATUS_LABEL, STATUS_TONE, credits, day, dollars } from './format'
import { useLoad } from './useLoad'

interface Column {
  key: PlayerSortKey | null
  label: string
  numeric?: boolean
}

const COLUMNS: readonly Column[] = [
  { key: 'name', label: 'Player' },
  { key: null, label: 'Status' },
  { key: null, label: 'Plan' },
  { key: 'balance', label: 'Balance', numeric: true },
  { key: 'used', label: 'Used, 30 days', numeric: true },
  { key: 'cost', label: 'API cost, 30 days', numeric: true },
  { key: 'games', label: 'Games', numeric: true },
  { key: 'last_active', label: 'Last active' },
  { key: 'joined', label: 'Joined' },
]

interface PlayersPanelProps {
  api: OwnerApi
  filters: PlayerFilters
  onFilters: (filters: PlayerFilters) => void
}

/** Every player (SPEC_V4 §10.2): searched, filtered, sorted and paged on the server. */
export function PlayersPanel({ api, filters, onFilters }: PlayersPanelProps) {
  const { load, reload } = useLoad(() => api.players(filters), playerQuery(filters))
  const change = (update: PlayerFilters) => onFilters({ ...filters, ...update, page: update.page ?? 1 })
  const sort = filters.sort ?? '-joined'
  return (
    <div className="owner-players">
      <PlayerFiltersForm filters={filters} onChange={change} />
      {load.kind === 'loading' && <Skeleton lines={8} label="Loading players…" />}
      {load.kind === 'error' && <ErrorState message={load.message} onRetry={reload} />}
      {load.kind === 'ready' && load.data.total === 0 && (
        <EmptyState title="No players match">
          <p>Clear the search or a filter to see more players.</p>
        </EmptyState>
      )}
      {load.kind === 'ready' && load.data.total > 0 && (
        <>
          <p className="owner-quiet" role="status">
            {load.data.total.toLocaleString()} {load.data.total === 1 ? 'player' : 'players'}
          </p>
          <Table className="owner-table" aria-label="Players">
            <thead>
              <tr>
                {COLUMNS.map((column) => (
                  <SortHeader key={column.label} column={column} sort={sort} onSort={(next) => change({ sort: next })} />
                ))}
              </tr>
            </thead>
            <tbody>
              {load.data.rows.map((row) => (
                <PlayerLine key={row.id} row={row} />
              ))}
            </tbody>
          </Table>
          <Pager
            page={load.data.page}
            total={load.data.total}
            size={load.data.page_size}
            onPage={(page) => change({ page })}
          />
        </>
      )}
    </div>
  )
}

function PlayerFiltersForm({ filters, onChange }: { filters: PlayerFilters; onChange: (f: PlayerFilters) => void }) {
  const [query, setQuery] = useState(filters.q ?? '')
  function search(event: FormEvent) {
    event.preventDefault()
    onChange({ q: query.trim() || undefined })
  }
  return (
    <form className="owner-filters" role="search" onSubmit={search}>
      <div className="owner-search">
        <Input label="Search" placeholder="Name or email" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button type="submit" variant="outline">
          Search
        </Button>
      </div>
      <Select
        label="Status"
        value={filters.status ?? ''}
        onChange={(e) => onChange({ status: (e.target.value || undefined) as PlayerStatus | undefined })}
      >
        <option value="">Any</option>
        {(Object.keys(STATUS_LABEL) as PlayerStatus[]).map((status) => (
          <option key={status} value={status}>
            {STATUS_LABEL[status]}
          </option>
        ))}
      </Select>
      <Select
        label="Plan"
        value={filters.plan ?? ''}
        onChange={(e) => onChange({ plan: (e.target.value || undefined) as PlayerPlan | undefined })}
      >
        <option value="">Any</option>
        {(Object.keys(PLAN_LABEL) as PlayerPlan[]).map((plan) => (
          <option key={plan} value={plan}>
            {PLAN_LABEL[plan]}
          </option>
        ))}
      </Select>
      <Select
        label="Coach strength"
        value={filters.strength ?? ''}
        onChange={(e) => onChange({ strength: (e.target.value || undefined) as PlayerStrength | undefined })}
      >
        <option value="">Any</option>
        <option value="standard">Standard</option>
        <option value="deep">Deep</option>
      </Select>
      <label className="owner-check">
        <input
          type="checkbox"
          checked={filters.zero_credits ?? false}
          onChange={(e) => onChange({ zero_credits: e.target.checked || undefined })}
        />
        At zero credits
      </label>
    </form>
  )
}

function SortHeader({ column, sort, onSort }: { column: Column; sort: PlayerSort; onSort: (sort: PlayerSort) => void }) {
  const className = column.numeric ? 'owner-num' : undefined
  if (column.key === null) {
    return (
      <th scope="col" className={className}>
        {column.label}
      </th>
    )
  }
  const key = column.key
  const current = sort === key ? 'ascending' : sort === `-${key}` ? 'descending' : 'none'
  // Names read A to Z first; numbers and dates biggest or newest first.
  const first: PlayerSort = key === 'name' ? key : `-${key}`
  const next: PlayerSort = current === 'none' ? first : current === 'ascending' ? `-${key}` : key
  return (
    <th scope="col" className={className} aria-sort={current}>
      <button type="button" className="owner-sort" onClick={() => onSort(next)}>
        {column.label}
        <span aria-hidden="true" className="owner-sort-mark">
          {current === 'ascending' ? '↑' : current === 'descending' ? '↓' : ''}
        </span>
      </button>
    </th>
  )
}

function PlayerLine({ row }: { row: PlayerRow }) {
  return (
    <tr>
      <td>
        <Link to={`/owner/players/${encodeURIComponent(row.id)}`} className="owner-name">
          {row.name}
        </Link>
        <span className="owner-sub">{row.email ?? 'no email'}</span>
      </td>
      <td>
        <Pill tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Pill>
      </td>
      <td>
        {PLAN_LABEL[row.plan]}
        {row.unmetered && <span className="owner-sub">never charged</span>}
        {row.coach_strength === 'deep' && <span className="owner-sub">Deep coach</span>}
      </td>
      <td className="owner-num">{credits(row.balance_microusd)}</td>
      <td className="owner-num">{credits(row.used_30d_microusd)}</td>
      <td className="owner-num">{dollars(row.cost_30d_microusd)}</td>
      <td className="owner-num">{row.games.toLocaleString()}</td>
      <td>{day(row.last_active_at)}</td>
      <td>{day(row.joined_at)}</td>
    </tr>
  )
}

export function Pager({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size))
  if (pages === 1) return null
  return (
    <nav className="owner-pager" aria-label="Pages">
      <Button variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <span>
        Page {page} of {pages}
      </span>
      <Button variant="outline" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </nav>
  )
}
