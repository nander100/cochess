import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { type Theme, type ThemePreference, applyTheme, readStoredTheme, storeTheme, watchSystemTheme } from './theme'
import { ThemeContext } from './themeContext'

function browserStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

/** Holds the theme preference, keeps <html data-theme> in step with it, and follows the operating
 * system while the preference is "system". */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => readStoredTheme(browserStorage()))
  const [theme, setTheme] = useState<Theme>(() => applyTheme(preference))

  const setPreference = useCallback((next: ThemePreference) => {
    storeTheme(browserStorage(), next)
    setPreferenceState(next)
    setTheme(applyTheme(next))
  }, [])

  useEffect(() => {
    if (preference !== 'system') return undefined
    return watchSystemTheme(() => setTheme(applyTheme('system')))
  }, [preference])

  const toggle = useCallback(() => setPreference(theme === 'dark' ? 'light' : 'dark'), [setPreference, theme])

  const value = useMemo(() => ({ preference, theme, setPreference, toggle }), [preference, theme, setPreference, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
