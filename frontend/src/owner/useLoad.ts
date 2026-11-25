import { useCallback, useEffect, useRef, useState } from 'react'
import { errorText } from '../pages/util'

export type Load<T> = { kind: 'loading' } | { kind: 'ready'; data: T } | { kind: 'error'; message: string }

/** Load `fetch()` whenever `key` changes (a filter, a period, an id). `reload` asks again;
 * `replace` shows data an action returned. An answer for an older key is dropped. */
export function useLoad<T>(fetch: () => Promise<T>, key: string) {
  const [state, setState] = useState<{ key: string; load: Load<T> }>({ key, load: { kind: 'loading' } })
  const [attempt, setAttempt] = useState(0)
  const latest = useRef(fetch)

  useEffect(() => {
    latest.current = fetch
  })

  useEffect(() => {
    let live = true
    latest.current().then(
      (data) => live && setState({ key, load: { kind: 'ready', data } }),
      (error: unknown) => live && setState({ key, load: { kind: 'error', message: errorText(error) } }),
    )
    return () => {
      live = false
    }
  }, [key, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const replace = useCallback((data: T) => setState({ key, load: { kind: 'ready', data } }), [key])
  // A new key shows loading at once rather than the previous key's data.
  const load: Load<T> = state.key === key ? state.load : { kind: 'loading' }
  return { load, reload, replace }
}
