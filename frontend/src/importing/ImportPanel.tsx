import { type FormEvent, useId, useState } from 'react'
import { Link } from 'react-router'
import type { PipelineDeps } from '../analysis/pipeline'
import { type QueueProgress, queueLabel, runGamesQueue } from '../analysis/queue'
import { ApiError, isLoggedOut } from '../api/client'
import type { Color, ImportResponse, Platform, TimeControl } from '../api/types'
import { errorText } from '../pages/util'
import { useSettings } from '../settings/settingsContext'
import { Button, ProgressBar, Select, TintedPanel, useToast } from '../ui'
import { ImportTable } from './ImportTable'
import { type ImportChoice, PLATFORM_LABEL, initialChoices, missingColors, requestsFor } from './importRows'
import './ImportPanel.css'

const COUNTS = [10, 20, 50] as const
const TIME_CONTROLS: { value: TimeControl | ''; label: string }[] = [
  { value: '', label: 'Any time control' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'classical', label: 'Classical' },
  { value: 'bullet', label: 'Bullet' },
]

interface ImportPanelProps {
  deps: PipelineDeps
  onLoggedOut: () => void
  /** Games were added (and again once they're analyzed): the page reloads its lists. */
  onAdded: () => void
}

/** "Import recent games" (SPEC_V3 §10): fetch the player's latest games from Lichess or
 * Chess.com, review them, then add and analyze the ticked ones one after another. */
export function ImportPanel({ deps, onLoggedOut, onAdded }: ImportPanelProps) {
  const id = useId()
  const { api } = deps
  const { settings } = useSettings()
  const { show } = useToast()
  const names: Record<Platform, string> = { chesscom: settings.chesscom_username, lichess: settings.lichess_username }
  const platforms = (['chesscom', 'lichess'] as const).filter((p) => names[p].trim() !== '')
  const [picked, setPicked] = useState<Platform | null>(null)
  const platform = picked && platforms.includes(picked) ? picked : (platforms[0] ?? null)
  const [count, setCount] = useState<number>(20)
  const [tc, setTc] = useState<TimeControl | ''>('')
  const [since, setSince] = useState('')
  const [found, setFound] = useState<ImportResponse | null>(null)
  const [choices, setChoices] = useState<ImportChoice[]>([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<QueueProgress | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (platform === null) {
    return (
      <TintedPanel as="section" className="import-panel" aria-labelledby={`${id}-title`}>
        <h2 id={`${id}-title`} className="games-section-title">
          Import recent games
        </h2>
        <p className="import-note">
          <Link to="/profile">Add your Chess.com or Lichess username</Link> on your profile to bring in your latest
          games.
        </p>
      </TintedPanel>
    )
  }

  function failed(caught: unknown) {
    if (isLoggedOut(caught)) onLoggedOut()
    else if (caught instanceof ApiError && caught.status < 500) setError(errorText(caught))
    else show(errorText(caught), 'error')
  }

  async function fetchGames(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (platform === null) return
    setBusy(true)
    setError(null)
    try {
      const response = await api.importGames({ platform, max: count, tc: tc || null, since: since || null })
      setFound(response)
      setChoices(initialChoices(response.games))
    } catch (caught) {
      failed(caught)
    } finally {
      setBusy(false)
    }
  }

  async function addGames() {
    if (found === null) return
    const ticked = requestsFor(found.games, choices)
    // Imported games count toward the daily cap: add what fits today (owner decision 2026-11-06).
    const requests = ticked.slice(0, found.games_left_today)
    let leftOver = ticked.length - requests.length
    setBusy(true)
    setError(null)
    try {
      const ids: string[] = []
      let skipped = 0
      for (const [i, request] of requests.entries()) {
        try {
          ids.push((await api.createGame(request)).game_id)
        } catch (caught) {
          // Added since the table was fetched (another tab, the assessment): nothing to do.
          if (caught instanceof ApiError && caught.status === 409 && caught.message.includes('already')) skipped += 1
          // Today's cap reached meanwhile (a game pasted in another tab): stop, keep what's added.
          else if (caught instanceof ApiError && caught.status === 429) {
            leftOver += requests.length - i
            break
          } else throw caught
        }
      }
      setFound(null)
      onAdded()
      await runGamesQueue(deps, ids, setProgress)
      const extra = skipped > 0 ? ` (${skipped} ${skipped === 1 ? 'was' : 'were'} already here)` : ''
      const later = leftOver > 0 ? ` Today's limit is reached: import the other ${plural(leftOver)} tomorrow.` : ''
      show(`Added and analyzed ${plural(ids.length)}${extra}.${later}`, 'info')
    } catch (caught) {
      failed(caught)
    } finally {
      setProgress(null)
      setBusy(false)
      onAdded()
    }
  }

  const rows = found?.games ?? []
  const ticked = found ? requestsFor(rows, choices).length : 0
  const toAdd = Math.min(ticked, found?.games_left_today ?? 0)
  const missing = found ? missingColors(rows, choices) : 0

  return (
    <TintedPanel as="section" className="import-panel" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="games-section-title">
        Import recent games
      </h2>
      <form className="import-form" onSubmit={(event) => void fetchGames(event)} aria-label="Import recent games">
        <Select label="From" value={platform} disabled={busy} onChange={(event) => setPicked(event.target.value as Platform)}>
          {platforms.map((p) => (
            <option key={p} value={p}>
              {PLATFORM_LABEL[p]} ({names[p]})
            </option>
          ))}
        </Select>
        <Select label="How many" value={count} disabled={busy} onChange={(event) => setCount(Number(event.target.value))}>
          {COUNTS.map((n) => (
            <option key={n} value={n}>
              Last {n} games
            </option>
          ))}
        </Select>
        <Select
          label="Time control"
          value={tc}
          disabled={busy}
          onChange={(event) => setTc(event.target.value as TimeControl | '')}
        >
          {TIME_CONTROLS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
        <label className="import-since">
          <span className="ui-field-label">Played since</span>
          <input
            type="date"
            className="ui-input"
            value={since}
            disabled={busy}
            onChange={(event) => setSince(event.target.value)}
          />
        </label>
        <Button type="submit" variant="outline" disabled={busy}>
          {found ? 'Fetch again' : 'Fetch games'}
        </Button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {found && found.games.length === 0 && (
        <p className="import-note">No games found for {found.username} with these filters.</p>
      )}
      {found && found.games.length > 0 && (
        <>
          <ImportTable
            rows={rows}
            choices={choices}
            disabled={busy}
            onInclude={(index, include) => setChoices(update(choices, index, { include }))}
            onColor={(index, color: Color) => setChoices(update(choices, index, { color }))}
          />
          <div className="import-actions">
            <span className="import-note" role="status">
              {roomText(found.games_left_today, ticked)}
            </span>
            <Button variant="secondary" onClick={() => void addGames()} disabled={busy || toAdd === 0 || missing > 0}>
              {addLabel(missing, toAdd)}
            </Button>
          </div>
        </>
      )}
      {progress && <ProgressBar label={queueLabel(progress)} done={progress.game - 1} total={progress.total} />}
    </TintedPanel>
  )
}

function plural(n: number): string {
  return `${n} game${n === 1 ? '' : 's'}`
}

/** Today's room under the daily cap of new games, next to the Add button. */
function roomText(left: number, ticked: number): string {
  if (left === 0) return "You've added today's limit of new games. Import these tomorrow."
  const more = left === 1 ? '1 more game' : `${left} more games`
  if (ticked > left) return `Only ${more} can be added today, so the first ${left === 1 ? 'one' : left} ticked will be added.`
  return `You can add ${more} today.`
}

function addLabel(missing: number, toAdd: number): string {
  if (missing > 0) return `Choose your color for ${missing} game${missing === 1 ? '' : 's'}`
  if (toAdd === 0) return 'No games to add'
  return `Add and analyze ${toAdd} game${toAdd === 1 ? '' : 's'}`
}

function update(choices: readonly ImportChoice[], index: number, change: Partial<ImportChoice>): ImportChoice[] {
  return choices.map((choice, i) => (i === index ? { ...choice, ...change } : choice))
}
