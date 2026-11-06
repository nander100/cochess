import type { Color, ImportRow } from '../api/types'
import { CATEGORY_LABEL } from '../onboarding/labels'
import { Pill, Table } from '../ui'
import { type ImportChoice, addable } from './importRows'

interface ImportTableProps {
  rows: readonly ImportRow[]
  choices: readonly ImportChoice[]
  disabled: boolean
  onInclude: (index: number, include: boolean) => void
  onColor: (index: number, color: Color) => void
}

/** The fetched games to review (SPEC_V3 §10): tick the ones to add; the color is filled in from
 * the player's username where it appears, and chosen by the player otherwise. */
export function ImportTable({ rows, choices, disabled, onInclude, onColor }: ImportTableProps) {
  return (
    <Table className="import-table" aria-label="Fetched games">
      <thead>
        <tr>
          <th scope="col">
            <span className="visually-hidden">Add</span>
          </th>
          <th scope="col">Players</th>
          <th scope="col">Result</th>
          <th scope="col">Date</th>
          <th scope="col">Time control</th>
          <th scope="col">I played</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => {
          const choice = choices[i]
          const label = `${row.white ?? '?'} vs ${row.black ?? '?'}`
          return (
            <tr key={row.external_id} className={addable(row) ? undefined : 'import-unused'}>
              <td>
                {addable(row) && (
                  <input
                    type="checkbox"
                    aria-label={`Add ${label}`}
                    checked={choice?.include ?? false}
                    disabled={disabled}
                    onChange={(event) => onInclude(i, event.target.checked)}
                  />
                )}
              </td>
              <td className="import-players">
                {row.url ? (
                  <a href={row.url} target="_blank" rel="noopener noreferrer">
                    {label}
                  </a>
                ) : (
                  label
                )}
              </td>
              <td className="numeric">{row.result ?? '?'}</td>
              <td className="import-muted">{row.date ?? '—'}</td>
              <td className="import-muted">{row.category ? CATEGORY_LABEL[row.category] : (row.time_control ?? '—')}</td>
              <td>
                <ColorCell row={row} choice={choice} label={label} disabled={disabled} onColor={(c) => onColor(i, c)} />
              </td>
            </tr>
          )
        })}
      </tbody>
    </Table>
  )
}

interface ColorCellProps {
  row: ImportRow
  choice: ImportChoice | undefined
  label: string
  disabled: boolean
  onColor: (color: Color) => void
}

function ColorCell({ row, choice, label, disabled, onColor }: ColorCellProps) {
  if (row.already_imported) return <Pill tone="neutral">Already added</Pill>
  if (row.error || row.pgn === null) return <span className="import-muted">Can't be analyzed: {row.error?.message}</span>
  return (
    <>
      <select
        className="ui-input ui-select import-select"
        aria-label={`Your color in ${label}`}
        value={choice?.color ?? ''}
        disabled={disabled || !choice?.include}
        onChange={(event) => onColor(event.target.value as Color)}
      >
        <option value="" disabled>
          Choose…
        </option>
        <option value="white">White</option>
        <option value="black">Black</option>
      </select>
      {row.user_color && choice?.color === row.user_color && <span className="import-hint">From your username</span>}
    </>
  )
}
