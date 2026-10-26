import { formatEval, positionLabel } from './format'

test.each([
  [{ eval_cp: 34, mate: null }, '+0.3'],
  [{ eval_cp: -200, mate: null }, '-2.0'],
  [{ eval_cp: -4, mate: null }, '0.0'],
  [{ eval_cp: 1550, mate: null }, '+15.5'],
  [{ eval_cp: null, mate: 3 }, '+M3'],
  [{ eval_cp: null, mate: -2 }, '-M2'],
])('formats %o as %s', (line, text) => {
  expect(formatEval(line)).toBe(text)
})

test('labels positions by the move about to be played', () => {
  expect(positionLabel(27, 40)).toBe('before 14.')
  expect(positionLabel(28, 40)).toBe('before 14...')
  expect(positionLabel(41, 40)).toBe('final position')
  expect(positionLabel(null, 40)).toBe('—')
})
