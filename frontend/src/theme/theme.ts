/** Light / dark / match-system themes (SPEC_V3 §4.1, docs/design/tokens.md). The preference is a
 * per-user setting; it is also kept in localStorage so index.html can apply it before React loads
 * and the page never flashes the wrong theme. The document only ever gets "light" or "dark". */

export type ThemePreference = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'

export const THEME_KEY = 'cochess-theme'
export const DEFAULT_THEME: ThemePreference = 'light'
const DARK_QUERY = '(prefers-color-scheme: dark)'

export function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): Theme {
  if (preference === 'system') return systemPrefersDark ? 'dark' : 'light'
  return preference
}

export function readStoredTheme(storage: Pick<Storage, 'getItem'> | null): ThemePreference {
  try {
    const value = storage?.getItem(THEME_KEY)
    return isThemePreference(value) ? value : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

export function storeTheme(storage: Pick<Storage, 'setItem'> | null, preference: ThemePreference): void {
  try {
    storage?.setItem(THEME_KEY, preference)
  } catch {
    // Private mode or blocked storage: the theme still applies for this page.
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(DARK_QUERY).matches
}

/** Put the resolved theme on <html>. */
export function applyTheme(preference: ThemePreference, root: HTMLElement = document.documentElement): Theme {
  const theme = resolveTheme(preference, systemPrefersDark())
  root.dataset.theme = theme
  return theme
}

/** Follow the operating system while the preference is "system". Returns an unsubscribe. */
export function watchSystemTheme(onChange: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {}
  const media = window.matchMedia(DARK_QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}
