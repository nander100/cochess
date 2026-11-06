import type { Annotation } from '../api/types'
import { COACH_BRUSH, coachBrushes, latestByPath, toShapes } from './coachShapes'

const TAG: Annotation = {
  tag_index: 0,
  char_offset: 0,
  arrows: [{ orig: 'c4', dest: 'f7', color: 'red' }],
  squares: [{ square: 'f7', color: 'yellow' }],
}

test('arrows become arrows and squares become circles, in the coach brushes', () => {
  expect(toShapes([TAG])).toEqual([
    { orig: 'c4', dest: 'f7', brush: 'coachRed' },
    { orig: 'f7', brush: 'coachYellow' },
  ])
})

test('the coach brushes are separate from the player\'s and use the chess-meaning tokens', () => {
  const read = vi.fn((name: string) => `color(${name})`)

  const brushes = coachBrushes(read)

  expect(Object.keys(brushes)).toEqual(Object.values(COACH_BRUSH))
  expect(Object.keys(brushes)).not.toContain('green')
  expect(brushes.coachGreen.color).toBe('color(--chess-good)')
  expect(brushes.coachRed.color).toBe('color(--chess-blunder)')
  expect(brushes.coachYellow.color).toBe('color(--chess-inaccuracy)')
  expect(brushes.coachBlue.color).toBe('color(--chess-plan)')
  expect(new Set(Object.values(brushes).map((b) => b.key)).size).toBe(4)
})

test('the latest coach message about a position decides what is drawn there', () => {
  const latest = latestByPath([
    { role: 'coach', path: 'e2e4', annotations: [TAG] },
    { role: 'player', path: 'e2e4' },
    { role: 'coach', path: '', annotations: [TAG] },
    { role: 'coach', path: 'e2e4', annotations: [] },
    { role: 'coach', path: null, annotations: [TAG] },
  ])

  expect([...latest.entries()]).toEqual([
    ['e2e4', []],
    ['', [TAG]],
  ])
})
