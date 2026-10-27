import { errorText, gameDate, tokenFromHash } from './util'

test.each([
  ['#token=abc-_123', 'abc-_123'],
  ['token=abc', 'abc'],
  ['#token=', null],
  ['#other=1', null],
  ['', null],
])('reads the login token from the fragment %j', (hash, expected) => {
  expect(tokenFromHash(hash)).toBe(expected)
})

test('error text uses the error message, or a generic one', () => {
  expect(errorText(new Error('Game not found.'))).toBe('Game not found.')
  expect(errorText('nope')).toBe('Something went wrong.')
})

test('game dates are shown as the UTC date, not shifted by the local timezone', () => {
  // Midnight UTC is the evening before in the Americas; the PGN said January 1st.
  expect(gameDate('2026-01-01T00:00:00Z')).toBe(
    new Date(Date.UTC(2026, 0, 1, 12)).toLocaleDateString(undefined, { dateStyle: 'medium' }),
  )
})
