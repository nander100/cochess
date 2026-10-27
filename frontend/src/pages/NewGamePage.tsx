import { useState } from 'react'
import { useNavigate } from 'react-router'
import { type AnalysisStatus, type PipelineDeps, runAnalysis, statusLabel } from '../analysis/pipeline'
import { isLoggedOut } from '../api/client'
import type { CreateGameRequest } from '../api/types'
import { GameInput } from '../components/GameInput'
import { ProgressBar } from '../components/ProgressBar'
import type { FreshAnalysis } from './GamePage'
import { errorText } from './util'

interface NewGamePageProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

/** Paste a game, run the engine on it, then open it on the analysis board. */
export function NewGamePage({ deps, onLoggedOut }: NewGamePageProps) {
  const navigate = useNavigate()
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function analyze(request: CreateGameRequest) {
    setError(null)
    setStatus({ phase: 'starting' })
    try {
      const run = await runAnalysis(deps, request, setStatus)
      const state: FreshAnalysis = { run }
      navigate(`/games/${run.game.game_id}`, { state })
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
      setStatus(null)
    }
  }

  return (
    <>
      <GameInput disabled={status !== null} onSubmit={(request) => void analyze(request)} />
      {status && (
        <ProgressBar
          label={statusLabel(status)}
          {...(status.phase === 'starting' ? { done: 0, total: 1 } : status)}
        />
      )}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
    </>
  )
}
