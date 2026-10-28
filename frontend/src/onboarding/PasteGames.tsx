import { type FormEvent, useId, useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Color, GameChoice, ParseResponse, ParsedRow, SubmitGame, TimeControl } from '../api/types'
import { errorText } from '../pages/util'
import { CATEGORY_LABEL, PICKABLE, SLOT_LABEL, reasonText } from './labels'

interface PasteGamesProps {
  api: ApiClient
  onAdded: () => void
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
  const [added, setAdded] = useState<string | null>(null)

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
    setAdded(null)
    const response = await run(() => api.onboardingParse(text, []))
    if (response) {
      setParsed(response)
      setChoices(response.games.map(() => null))
    }
  }

  async function choose(index: number, change: GameChoice) {
    const next = choices.map((choice, i) => (i === index ? { ...choice, ...change } : choice))
    setChoices(next)
    const response = await run(() => api.onboardingParse(text, next))
    if (response) setParsed(response)
  }

  const usable = parsed?.games.filter((row) => row.slot !== null && row.pgn !== null) ?? []

  async function add() {
    const games: SubmitGame[] = usable.map((row) => ({
      pgn: row.pgn ?? '',
      user_color: row.user_color ?? 'white',
      time_control_category: choices[row.index]?.time_control_category ?? null,
    }))
    const response = await run(() => api.onboardingSubmit(games))
    if (!response) return
    const count = response.results.filter((result) => result.game_id !== null).length
    setAdded(`Added ${count} game${count === 1 ? '' : 's'}.`)
    setText('')
    setParsed(null)
    setChoices([])
    onAdded()
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
      {added && <p role="status">{added}</p>}
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
                  onChoose={(change) => void choose(row.index, change)}
                />
              ))}
            </tbody>
          </table>
          <button type="button" onClick={() => void add()} disabled={busy || usable.length === 0}>
            {usable.length === 0 ? 'No games to add' : `Add ${usable.length} game${usable.length === 1 ? '' : 's'}`}
          </button>
        </>
      )}
    </section>
  )
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
    <tr className={row.slot ? 'fills' : 'unused'}>
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
      </td>
      <td>{row.slot ? SLOT_LABEL[row.slot] : <span className="slot-reason">{reason}</span>}</td>
    </tr>
  )
}
