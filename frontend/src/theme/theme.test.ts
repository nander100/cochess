import { THEME_KEY, applyTheme, readStoredTheme, resolveTheme, storeTheme } from './theme'

function mediaReturning(matches: boolean) {
  return vi.fn(() => ({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
}

test('light is the default when nothing valid is stored', () => {
  expect(readStoredTheme(null)).toBe('light')
  expect(readStoredTheme({ getItem: () => 'purple' })).toBe('light')
  expect(readStoredTheme({ getItem: () => { throw new Error('blocked') } })).toBe('light')
})

test('a stored preference is read back', () => {
  const values = new Map<string, string>()
  storeTheme({ setItem: (k, v) => values.set(k, v) }, 'system')

  expect(values.get(THEME_KEY)).toBe('system')
  expect(readStoredTheme({ getItem: (k) => values.get(k) ?? null })).toBe('system')
})

test('"match system" resolves to the operating system theme', () => {
  expect(resolveTheme('system', true)).toBe('dark')
  expect(resolveTheme('system', false)).toBe('light')
  expect(resolveTheme('dark', false)).toBe('dark')
  expect(resolveTheme('light', true)).toBe('light')
})

test('the document only ever gets light or dark', () => {
  vi.stubGlobal('matchMedia', mediaReturning(true))
  const root = document.createElement('html')

  expect(applyTheme('system', root)).toBe('dark')
  expect(root.dataset.theme).toBe('dark')
  applyTheme('light', root)
  expect(root.dataset.theme).toBe('light')
  vi.unstubAllGlobals()
})
