import { createContext, useContext } from 'react'
import type { UserSettings } from '../api/types'

export const DEFAULT_SETTINGS: UserSettings = {
  theme: 'light',
  board_scheme: 'blue',
  piece_set: 'cburnett',
  sounds: false,
  engine_panel: false,
  coach_detail_level: 'auto',
  effective_detail_level: 'standard', // replaced by the server's answer once settings load
  playback_seconds: 1.5,
}

export interface SettingsState {
  settings: UserSettings
  /** True once the player's saved settings have loaded. */
  loaded: boolean
  /** Apply at once, then save; a failed save is reported and undone. */
  update: (change: Partial<UserSettings>) => void
}

export const SettingsContext = createContext<SettingsState>({
  settings: DEFAULT_SETTINGS,
  loaded: false,
  update: () => {},
})

export function useSettings(): SettingsState {
  return useContext(SettingsContext)
}
