import { errorText, tokenFromHash } from './util'

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
