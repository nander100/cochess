import { type FormEvent, useId, useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Color, GameChoice, ParseResponse, ParsedRow, SubmitGame, TimeControl } from '../api/types'
import { errorText } from '../pages/util'
import { CATEGORY_LABEL, PICKABLE, SLOT_LABEL, reasonText } from './labels'

interface PasteGamesProps {
  api: ApiClient
  /** Called with a confirmation ("Added 3 games."); the page shows it, since this form goes
   * away once every slot is filled. */
  onAdded: (message: string) => void
  onLoggedOut: () => void
}

/** Paste games, check which slot each fills (SPEC_V2 §10.3 step 3), then add them. The table is
 * the server's preview: it decides again when the games are added. */
export function PasteGames({ api, onAdded, onLoggedOut }: PasteGamesProps) {
  const id = useId()
  const [text, setText] = useState('')
  const [parsed, setParsed] = useState<ParseResponse | null>(null)
  const [choices, setChoices] = useState<(GameChoice | null)[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run<T>(work: () => Promise<T>): Promise<T | null> {
    setBusy(true)
    setError(null)
    try {
      return await work()
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
      return null
    } finally {
      setBusy(false)
    }
  }

  async function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) return
    const response = await run(() => api.onboardingParse(text, []))
    if (response) {
      setParsed(response)
      setChoices(response.games.map(() => null))
    }
  }

  async function apply(next: (GameChoice | null)[]) {
    setChoices(next)
    const response = await run(() => api.onboardingParse(text, next))
    if (response) setParsed(response)
  }

  function choose(index: number, change: GameChoice) {
    void apply(choices.map((choice, i) => (i === index ? { ...choice, ...change } : choice)))
  }

  /** Copy each detected color into the player's choice. The player asks for this; nothing is
   * pre-selected (SPEC_V3 §4.6). */
  function applyDetected() {
    const rows = parsed?.games ?? []
    void apply(
      choices.map((choice, i) => {
        const suggested = rows[i]?.suggested_color
        return suggested && !choice?.user_color ? { ...choice, user_color: suggested } : choice
      }),
    )
  }

  const rows = parsed?.games ?? []
  const missingColor = rows.filter(needsColor)
  const detectable = missingColor.some((row) => row.suggested_color !== null)
  const usable = rows.flatMap((row) =>
    row.slot !== null && row.pgn !== null && row.user_color !== null
      ? [{ pgn: row.pgn, user_color: row.user_color, index: row.index }]
      : [],
  )

  async function add() {
    if (missingColor.length > 0) return
    const games: SubmitGame[] = usable.map((row) => ({
      pgn: row.pgn,
      user_color: row.user_color,
      time_control_category: choices[row.index]?.time_control_category ?? null,
    }))
    const response = await run(() => api.onboardingSubmit(games))
    if (!response) return
    const count = response.results.filter((result) => result.game_id !== null).length
    setText('')
    setParsed(null)
    setChoices([])
    onAdded(`Added ${count} game${count === 1 ? '' : 's'}.`)
  }

  return (
    <section className="panel paste-games" aria-label="Add games">
      <form onSubmit={(event) => void check(event)}>
        <label htmlFor={`${id}-pgn`}>Paste one or more games (PGN)</label>
        <textarea
          id={`${id}-pgn`}
          className="pgn"
          rows={6}
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            setParsed(null)
          }}
          disabled={busy}
          placeholder={'[Event "Rated rapid game"]\n...\n\n[Event "Rated rapid game"]\n...'}
        />
        <button type="submit" disabled={busy || !text.trim()}>
          Check games
        </button>
      </form>
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
      {parsed && (
        <>
          <table className="paste-table">
            <thead>
              <tr>
                <th scope="col">White</th>
                <th scope="col">Black</th>
                <th scope="col">Result</th>
                <th scope="col">Date</th>
                <th scope="col">Time control</th>
                <th scope="col">You played</th>
                <th scope="col">Slot</th>
              </tr>
            </thead>
            <tbody>
              {parsed.games.map((row) => (
                <Row
                  key={row.index}
                  row={row}
                  primary={parsed.primary_time_control}
                  disabled={busy}
                  onChoose={(change) => choose(row.index, change)}
                />
              ))}
            </tbody>
          </table>
          <div className="paste-actions">
            <button
              type="button"
              onClick={() => void add()}
              disabled={busy || missingColor.length > 0 || usable.length === 0}
            >
              {addLabel(missingColor.length, usable.length)}
            </button>
            {detectable && (
              <button type="button" className="secondary" onClick={applyDetected} disabled={busy}>
                Use detected colors
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}

/** A game the player can still use, but hasn't said which side they played. */
function needsColor(row: ParsedRow): boolean {
  return row.error === null && row.user_color === null
}

function plural(n: number): string {
  return `${n} game${n === 1 ? '' : 's'}`
}

function addLabel(missing: number, usable: number): string {
  if (missing > 0) return `Choose your color for ${plural(missing)}`
  return usable === 0 ? 'No games to add' : `Add ${plural(usable)}`
}

interface RowProps {
  row: ParsedRow
  primary: TimeControl
  disabled: boolean
  onChoose: (change: GameChoice) => void
}

function Row({ row, primary, disabled, onChoose }: RowProps) {
  const reason = reasonText(row, primary)
  const label = `game ${row.index + 1}`
  return (
    <tr className={needsColor(row) ? 'needs-color' : row.slot ? 'fills' : 'unused'}>
      <td>{row.white ?? '?'}</td>
      <td>{row.black ?? '?'}</td>
      <td>{row.result ?? '?'}</td>
      <td>{row.date ?? '—'}</td>
      <td>
        {row.category || row.error ? (
          row.category ? CATEGORY_LABEL[row.category] : '—'
        ) : (
          <select
            aria-label={`Time control for ${label}`}
            defaultValue=""
            disabled={disabled}
            onChange={(event) => onChoose({ time_control_category: event.target.value as TimeControl })}
          >
            <option value="" disabled>
              Choose…
            </option>
            {PICKABLE.map((tc) => (
              <option key={tc} value={tc}>
                {CATEGORY_LABEL[tc]}
              </option>
            ))}
          </select>
        )}
      </td>
      <td>
        {row.error ? (
          '—'
        ) : (
          <select
            aria-label={`Your color in ${label}`}
            value={row.user_color ?? ''}
            disabled={disabled}
            onChange={(event) => onChoose({ user_color: event.target.value as Color })}
          >
            <option value="" disabled>
              Choose…
            </option>
            <option value="white">White</option>
            <option value="black">Black</option>
          </select>
        )}
        {needsColor(row) && row.suggested_color && (
          <span className="color-hint">
            Detected: you played {row.suggested_color === 'white' ? 'White' : 'Black'}
          </span>
        )}
      </td>
      <td>{row.slot ? SLOT_LABEL[row.slot] : <span className="slot-reason">{reason}</span>}</td>
    </tr>
  )
}
