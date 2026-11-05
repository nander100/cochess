import { useCallback, useEffect, useRef } from 'react'
import { type ApiClient, ApiError, isLoggedOut } from '../api/client'
import type { SavedVariation } from '../api/types'
import { useToast } from '../ui'
import type { GameTree } from './tree'
import { variationsOf } from './variations'

/** How long the board waits after the last change before saving (SPEC_V3 §5.1: debounced). */
export const SAVE_DELAY_MS = 1000

export const SAVE_FAILED = "Your variations couldn't be saved. They'll be saved with your next move."

interface Saver {
  /** Save the tree's variations once the player pauses. */
  schedule: (tree: GameTree) => void
  /** Save anything still waiting now (before an export, or when leaving the page). */
  flush: () => Promise<void>
}

/** Auto-saves the player's variations for one game. `initial` is what the server already has
 * (null if nothing was saved yet), so an unchanged list isn't sent again. */
export function useVariationSaver(
  api: ApiClient,
  gameId: string,
  initial: readonly SavedVariation[] | null | undefined,
  onLoggedOut: () => void,
): Saver {
  const { show } = useToast()
  const pending = useRef<SavedVariation[] | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const saved = useRef<string | null>(initial ? JSON.stringify(initial) : null)
  // Callbacks change identity between renders; the saver must not, or the cleanup below would
  // save on every render instead of once the player pauses.
  const latest = useRef({ api, gameId, onLoggedOut, show })
  useEffect(() => {
    latest.current = { api, gameId, onLoggedOut, show }
  })

  const flush = useCallback(async () => {
    clearTimeout(timer.current)
    const variations = pending.current
    pending.current = null
    if (variations === null) return
    const key = JSON.stringify(variations)
    if (key === saved.current) return
    const { api, gameId, onLoggedOut, show } = latest.current
    try {
      await api.saveVariations(gameId, variations)
      saved.current = key
    } catch (error) {
      if (isLoggedOut(error)) onLoggedOut()
      else if (!(error instanceof ApiError && error.status === 404)) show(SAVE_FAILED, 'error')
      // 404: the game was just deleted, so there's nothing to save to.
    }
  }, [])

  const schedule = useCallback(
    (tree: GameTree) => {
      pending.current = variationsOf(tree)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => void flush(), SAVE_DELAY_MS)
    },
    [flush],
  )

  // Leaving the game saves what's waiting rather than dropping it.
  useEffect(() => () => void flush(), [flush])

  return { schedule, flush }
}
