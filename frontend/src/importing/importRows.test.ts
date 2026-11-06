import { importRow } from '../test/fakes'
import { addable, initialChoices, missingColors, requestsFor } from './importRows'

const SEEN = importRow(1, { already_imported: true })
const BROKEN = importRow(2, { pgn: null, error: { code: 'illegal_move', message: 'Illegal move', move_number: 3 } })
const UNKNOWN = importRow(3, { user_color: null })

test('only new games that parsed can be added, and they start ticked with the detected color', () => {
  const rows = [importRow(0), SEEN, BROKEN, UNKNOWN]

  expect(rows.map(addable)).toEqual([true, false, false, true])
  expect(initialChoices(rows)).toEqual([
    { include: true, color: 'white' },
    { include: false, color: 'white' },
    { include: false, color: 'white' },
    { include: true, color: null },
  ])
})

test('a ticked game without a color holds the others back until it has one', () => {
  const rows = [importRow(0), UNKNOWN]
  const choices = initialChoices(rows)

  expect(missingColors(rows, choices)).toBe(1)
  expect(missingColors(rows, [choices[0], { include: false, color: null }])).toBe(0)
  expect(missingColors(rows, [choices[0], { include: true, color: 'black' }])).toBe(0)
})

test('each upload carries its platform id', () => {
  const rows = [importRow(0), SEEN, UNKNOWN]
  const choices = [{ include: true, color: 'white' as const }, { include: true, color: 'white' as const },
                   { include: true, color: 'black' as const }] // prettier-ignore

  expect(requestsFor(rows, choices)).toEqual([
    { pgn: rows[0].pgn, user_color: 'white', external: { platform: 'chesscom', external_id: '1000' } },
    { pgn: rows[2].pgn, user_color: 'black', external: { platform: 'chesscom', external_id: '1003' } },
  ])
})
