import { useEffect, useRef } from 'react'
import { type ShortcutId, shortcutFor } from './shortcuts'

export type ShortcutHandlers = Partial<Record<ShortcutId, (() => void) | null>>

/** Handle shortcuts on the whole page. A handler set to null (or left out) leaves the key alone,
 * so it can be disabled, e.g. E and X during an unsolved moment. The latest handlers are used
 * without re-binding the listener. */
export function useShortcuts(handlers: ShortcutHandlers): void {
  const current = useRef(handlers)
  useEffect(() => {
    current.current = handlers
  })

  useEffect(() => {
    function handle(event: KeyboardEvent) {
      if (event.defaultPrevented) return
      const id = shortcutFor(event)
      const run = id ? current.current[id] : null
      if (!run) return
      event.preventDefault()
      run()
    }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [])
}
