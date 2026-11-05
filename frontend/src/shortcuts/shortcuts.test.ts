import { shortcutFor } from './shortcuts'

const press = (key: string, extra: Partial<KeyboardEvent> = {}, target: EventTarget | null = document.body) =>
  shortcutFor({ key, altKey: false, ctrlKey: false, metaKey: false, target, ...extra })

test('keys map to the shortcuts in SPEC_V3 §4.4', () => {
  expect(press('ArrowLeft')).toBe('prev')
  expect(press('ArrowRight')).toBe('next')
  expect(press('ArrowUp')).toBe('start')
  expect(press('Home')).toBe('start')
  expect(press('ArrowDown')).toBe('end')
  expect(press('End')).toBe('end')
  expect(press('f')).toBe('flip')
  expect(press('E')).toBe('engine')
  expect(press('x')).toBe('explain')
  expect(press('n')).toBe('nextMoment')
  expect(press('/')).toBe('focusChat')
  expect(press('?')).toBe('help')
  expect(press('Escape')).toBe('escape')
  expect(press('q')).toBeNull()
})

test('shortcuts are ignored while typing, except Esc', () => {
  const textarea = document.createElement('textarea')
  const text = Object.assign(document.createElement('input'), { type: 'text' })
  const checkbox = Object.assign(document.createElement('input'), { type: 'checkbox' })

  expect(press('f', {}, textarea)).toBeNull()
  expect(press('ArrowLeft', {}, text)).toBeNull()
  expect(press('Escape', {}, text)).toBe('escape')
  expect(press('ArrowLeft', {}, checkbox)).toBe('prev') // not a text box
})

test('Ctrl, Alt and Cmd combinations belong to the browser', () => {
  expect(press('f', { ctrlKey: true })).toBeNull()
  expect(press('ArrowLeft', { altKey: true })).toBeNull()
  expect(press('x', { metaKey: true })).toBeNull()
})
