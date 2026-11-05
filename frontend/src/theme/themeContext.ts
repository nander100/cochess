import { createContext, useContext } from 'react'
import { DEFAULT_THEME, type Theme, type ThemePreference } from './theme'

export interface ThemeState {
  /** What the player chose: light, dark, or match system. */
  preference: ThemePreference
  /** What the page shows now. */
  theme: Theme
  setPreference: (preference: ThemePreference) => void
  /** The header button: switch to the other of light and dark. */
  toggle: () => void
}

export const ThemeContext = createContext<ThemeState>({
  preference: DEFAULT_THEME,
  theme: 'light',
  setPreference: () => {},
  toggle: () => {},
})

export function useTheme(): ThemeState {
  return useContext(ThemeContext)
}
