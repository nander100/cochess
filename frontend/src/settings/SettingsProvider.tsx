import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { UserSettings } from '../api/types'
import { useTheme } from '../theme/themeContext'
import { useToast } from '../ui'
import { DEFAULT_SETTINGS, SettingsContext } from './settingsContext'

interface SettingsProviderProps {
  api: ApiClient
  /** Load and save only for a logged-in player. */
  enabled: boolean
  children: ReactNode
}

/** The player's settings (SPEC_V3 §4.3), stored per user on the server. The theme also lives in
 * localStorage (ThemeProvider) so the page paints in it before anything loads. Board colors and
 * the piece set are applied as data attributes on <html> (src/board/board.css). */
export function SettingsProvider({ api, enabled, children }: SettingsProviderProps) {
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS)
  const [loaded, setLoaded] = useState(false)
  const { setPreference } = useTheme()
  const { show } = useToast()
  const latest = useRef(settings)
  // What the player changed before their saved settings arrived: it wins over the saved values.
  const early = useRef<Partial<UserSettings>>({})

  useEffect(() => {
    latest.current = settings
  })

  useEffect(() => {
    if (!enabled) return
    let live = true
    api.settings().then(
      (saved) => {
        if (!live) return
        const merged = { ...saved, ...early.current }
        setSettings(merged)
        setLoaded(true)
        setPreference(merged.theme)
      },
      () => undefined, // keep the defaults; the page still works
    )
    return () => {
      live = false
    }
  }, [api, enabled, setPreference])

  // Board colors and pieces are CSS switches on <html>.
  useEffect(() => {
    const root = document.documentElement
    root.dataset.board = settings.board_scheme
    root.dataset.pieces = settings.piece_set
  }, [settings.board_scheme, settings.piece_set])

  const update = useCallback(
    (change: Partial<UserSettings>) => {
      const before = latest.current
      const next = { ...before, ...change }
      early.current = { ...early.current, ...change }
      setSettings(next)
      if (change.theme) setPreference(change.theme)
      if (!enabled) return
      api.updateSettings(change).then(setSettings, (caught: unknown) => {
        if (isLoggedOut(caught)) return
        setSettings(before)
        if (change.theme) setPreference(before.theme)
        show("Your setting couldn't be saved. Check your connection and try again.", 'error')
      })
    },
    [api, enabled, setPreference, show],
  )

  const value = useMemo(() => ({ settings, loaded, update }), [settings, loaded, update])
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}
