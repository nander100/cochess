import { type FormEvent, useId, useState } from 'react'
import { ApiError, type ApiClient, isLoggedOut } from '../api/client'
import type { Color, GameChoice, ParseResponse, ParsedRow, SubmitGame, TimeControl } from '../api/types'
import { Link } from 'react-router'
import { errorText } from '../pages/util'
import { useSettings, usernames } from '../settings/settingsContext'
import { Button, Pill, Table, useToast } from '../ui'
import { CATEGORY_LABEL, PICKABLE, SLOT_LABEL, reasonText } from './labels'
import './Onboarding.css'

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
  const { show } = useToast()
  const names = usernames(useSettings().settings)

  async function run<T>(work: () => Promise<T>): Promise<T | null> {
    setBusy(true)
    setError(null)
    try {
      return await work()
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else if (caught instanceof ApiError && caught.status === 422) setError(errorText(caught))
      else show(errorText(caught), 'error')
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

  const unusable = rows.filter((row) => row.slot === null && !needsColor(row)).length

  return (
    <section className="paste-games" aria-label="Add games">
      <form className="ui-tinted-panel paste-form" onSubmit={(event) => void check(event)}>
        <h2 className="paste-title">Add games</h2>
        <label className="paste-label" htmlFor={`${id}-pgn`}>
          Paste one or more games (PGN). We split them and check each one.
        </label>
        <p className="paste-note">
          {names.length > 0 ? (
            <>Your color in each game comes from your username ({names.join(', ')}).</>
          ) : (
            <>
              <Link to="/profile">Add your Chess.com or Lichess username</Link> and we'll fill in your color in
              each game.
            </>
          )}
        </p>
        <textarea
          id={`${id}-pgn`}
          className="ui-input ui-textarea ui-mono"
          rows={8}
          value={text}
          onChange={(event) => {
            setText(event.target.value)
            setParsed(null)
          }}
          disabled={busy}
          placeholder={'[Event "Rated rapid game"]\n1. e4 c5 ...\n\n[Event "Rated rapid game"]\n1. d4 Nf6 ...'}
        />
        <Button type="submit" className="paste-check" disabled={busy || !text.trim()}>
          Check games
        </Button>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
      {parsed && (
        <div className="paste-results">
          <h2 className="paste-subtitle">Checked games</h2>
          <Table className="paste-table" aria-label="Checked games">
            <thead>
              <tr>
                <th scope="col">Players</th>
                <th scope="col">Result</th>
                <th scope="col">Date</th>
                <th scope="col">Time control</th>
                <th scope="col">I played</th>
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
          </Table>
          <div className="paste-actions">
            <span className="paste-summary">
              {plural(usable.length)} can be added
              {unusable > 0 && ` · ${unusable} can't be used`}
              {missingColor.length > 0 && ` · ${plural(missingColor.length)} need${missingColor.length === 1 ? 's' : ''} a color`}
            </span>
            {detectable && (
              <Button variant="outline" onClick={applyDetected} disabled={busy}>
                Use detected colors
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={() => void add()}
              disabled={busy || missingColor.length > 0 || usable.length === 0}
            >
              {addLabel(missingColor.length, usable.length)}
            </Button>
          </div>
        </div>
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
      <td className="paste-players">
        {row.white ?? '?'} vs {row.black ?? '?'}
      </td>
      <td className="numeric">{row.result ?? '?'}</td>
      <td className="paste-muted">{row.date ?? '—'}</td>
      <td className="paste-muted">
        {row.category || row.error ? (
          row.category ? CATEGORY_LABEL[row.category] : '—'
        ) : (
          <select
            className="ui-input ui-select paste-select"
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
            className="ui-input ui-select paste-select"
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
        {row.color_detected && <span className="color-hint">From your username</span>}
        {needsColor(row) && row.suggested_color && (
          <span className="color-hint">
            Detected: you played {row.suggested_color === 'white' ? 'White' : 'Black'}
          </span>
        )}
      </td>
      <td>
        {row.slot ? (
          <Pill tone="analyzed">{SLOT_LABEL[row.slot]}</Pill>
        ) : (
          <span className="slot-reason">{reason}</span>
        )}
      </td>
    </tr>
  )
}
