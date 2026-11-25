import { useState } from 'react'
import { Link } from 'react-router'
import type { OwnerApi, PlayerRow } from '../api/ownerTypes'
import { errorText } from '../pages/util'
import { Button, EmptyState, ErrorState, Modal, Skeleton, Table, useToast } from '../ui'
import { dateTime, waited } from './format'
import { Pager } from './PlayersPanel'
import { useLoad } from './useLoad'

interface WaitlistPanelProps {
  api: OwnerApi
  page: number
  onPage: (page: number) => void
}

/** The waitlist (SPEC_V4 §10.2): oldest first, "Accept" on each row and for a selection. Each
 * acceptance gives the trial once and emails the player; it's confirmed first. */
export function WaitlistPanel({ api, page, onPage }: WaitlistPanelProps) {
  const toast = useToast()
  const query = () => api.players({ status: 'waitlisted', sort: 'waited', page })
  const { load, reload } = useLoad(query, `waitlist:${page}`)
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set())
  const [confirm, setConfirm] = useState<PlayerRow[] | null>(null)
  const [busy, setBusy] = useState(false)

  const rows = load.kind === 'ready' ? load.data.rows : []
  const chosen = rows.filter((row) => selected.has(row.id))
  const allChosen = rows.length > 0 && chosen.length === rows.length

  function toggle(id: string) {
    setSelected((was) => {
      const next = new Set(was)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function accept(players: PlayerRow[]) {
    setBusy(true)
    try {
      const result = await api.acceptMany(players.map((p) => p.id))
      const left = result.skipped.length ? ` ${result.skipped.join(', ')} had already left the waitlist.` : ''
      toast.show(`Accepted ${result.accepted} ${result.accepted === 1 ? 'player' : 'players'}.${left}`, 'info')
      setSelected(new Set())
      setConfirm(null)
      reload()
    } catch (error) {
      toast.show(errorText(error), 'error')
    } finally {
      setBusy(false)
    }
  }

  if (load.kind === 'loading') return <Skeleton lines={6} label="Loading the waitlist…" />
  if (load.kind === 'error') return <ErrorState message={load.message} onRetry={reload} />
  if (load.data.total === 0) {
    return (
      <EmptyState title="Nobody is waiting">
        <p>New sign-ups appear here, oldest first, until you accept them.</p>
      </EmptyState>
    )
  }
  const one = confirm?.length === 1 ? confirm[0] : null
  return (
    <div className="owner-waitlist">
      <div className="owner-toolbar">
        <p className="owner-quiet" role="status">
          {load.data.total.toLocaleString()} waiting · longest {waited(rows[0]?.waitlisted_at ?? null)}
        </p>
        <Button disabled={chosen.length === 0} onClick={() => setConfirm(chosen)}>
          Accept selected ({chosen.length})
        </Button>
      </div>
      <Table className="owner-table" aria-label="Waitlist">
        <thead>
          <tr>
            <th scope="col" className="owner-check-cell">
              <input
                type="checkbox"
                aria-label="Select everyone on this page"
                checked={allChosen}
                onChange={() => setSelected(allChosen ? new Set() : new Set(rows.map((r) => r.id)))}
              />
            </th>
            <th scope="col">Player</th>
            <th scope="col">Joined the waitlist</th>
            <th scope="col">Waiting</th>
            <th scope="col">
              <span className="visually-hidden">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="owner-check-cell">
                <input
                  type="checkbox"
                  aria-label={`Select ${row.name}`}
                  checked={selected.has(row.id)}
                  onChange={() => toggle(row.id)}
                />
              </td>
              <td>
                <Link to={`/owner/players/${encodeURIComponent(row.id)}`} className="owner-name">
                  {row.name}
                </Link>
                <span className="owner-sub">{row.email ?? 'no email'}</span>
              </td>
              <td>{row.waitlisted_at ? dateTime(row.waitlisted_at) : '–'}</td>
              <td>{waited(row.waitlisted_at)}</td>
              <td className="owner-num">
                <Button variant="outline" aria-label={`Accept ${row.name}`} onClick={() => setConfirm([row])}>
                  Accept
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pager page={load.data.page} total={load.data.total} size={load.data.page_size} onPage={onPage} />
      <Modal
        open={confirm !== null}
        title={one ? `Accept ${one.name}?` : `Accept ${confirm?.length ?? 0} players?`}
        onClose={() => !busy && setConfirm(null)}
        actions={
          <>
            <Button variant="outline" disabled={busy} onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button disabled={busy} onClick={() => confirm && void accept(confirm)}>
              {busy ? 'Accepting…' : 'Accept'}
            </Button>
          </>
        }
      >
        <p>
          {one ? 'They' : 'Each of them'} can sign in straight away, with the free trial credits, and gets an
          acceptance email.
        </p>
        {confirm && !one && (
          <ul className="owner-confirm-list">
            {confirm.map((row) => (
              <li key={row.id}>{row.name}</li>
            ))}
          </ul>
        )}
      </Modal>
    </div>
  )
}
