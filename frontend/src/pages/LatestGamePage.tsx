import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router'
import { type ApiClient, isLoggedOut } from '../api/client'
import { isUnsolved } from '../moments/moment'
import { EmptyState, ErrorState, Skeleton } from '../ui'
import { errorText } from './util'

export type LatestTarget = 'analysis' | 'moments'

interface LatestGamePageProps {
  api: ApiClient
  target: LatestTarget
  onLoggedOut: () => void
}

type State = { kind: 'loading' } | { kind: 'none' } | { kind: 'error'; message: string } | { kind: 'go'; to: string }

/** The nav's "Analysis" and "Critical moments" (docs/design/screens.md): open the most recent
 * game, or its first unfinished critical moment; with no games yet, say how to add one. */
export function LatestGamePage({ api, target, onLoggedOut }: LatestGamePageProps) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  const resolve = useCallback(async (): Promise<State> => {
    try {
      const [latest] = await api.listGames() // most recently played first
      if (!latest) return { kind: 'none' }
      if (target === 'analysis') return { kind: 'go', to: `/games/${latest.id}` }
      const detail = await api.getGame(latest.id)
      const moment = detail.moments.find(isUnsolved) ?? detail.moments[0]
      const query = moment ? `?view=moments&moment=${moment.index}` : '?view=moments'
      return { kind: 'go', to: `/games/${latest.id}${query}` }
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      return { kind: 'error', message: errorText(caught) }
    }
  }, [api, target, onLoggedOut])

  useEffect(() => {
    let live = true
    void resolve().then((next) => live && setState(next))
    return () => {
      live = false
    }
  }, [resolve])

  function retry() {
    setState({ kind: 'loading' })
    void resolve().then(setState)
  }

  switch (state.kind) {
    case 'loading':
      return <Skeleton label="Finding your latest game…" />
    case 'go':
      return <Navigate to={state.to} replace />
    case 'error':
      return <ErrorState message={state.message} onRetry={retry} />
    case 'none':
      return (
        <EmptyState
          title={target === 'analysis' ? 'No games to analyze yet' : 'No critical moments yet'}
          action={<Link to="/games">Analyze your first game</Link>}
        >
          <p>
            {target === 'analysis'
              ? 'Upload a game and the engine checks every move; then your coach explains it here.'
              : 'Critical moments come from your analyzed games: the turning points you get to replay.'}
          </p>
        </EmptyState>
      )
  }
}
