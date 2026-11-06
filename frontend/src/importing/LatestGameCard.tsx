import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { type AnalysisStatus, type PipelineDeps, runAnalysis, statusLabel } from '../analysis/pipeline'
import { ApiError, isLoggedOut } from '../api/client'
import type { ImportRow, Platform } from '../api/types'
import type { FreshAnalysis } from '../pages/GamePage'
import { errorText } from '../pages/util'
import { useSettings } from '../settings/settingsContext'
import { Button, FeatureCard, ProgressBar, useToast } from '../ui'
import { PLATFORM_LABEL } from './importRows'
import './LatestGameCard.css'

interface LatestGameCardProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

/** "Just played a game?" (owner request 2026-11-06): the first thing on the home page. One click
 * fetches the player's newest game from Chess.com or Lichess, analyzes it in the browser, and
 * opens it; a game they already have just opens. */
export function LatestGameCard({ deps, onLoggedOut }: LatestGameCardProps) {
  const navigate = useNavigate()
  const { show } = useToast()
  const { settings } = useSettings()
  const linked = (['chesscom', 'lichess'] as const).filter((p) => usernameOf(settings, p).trim() !== '')
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function analyzeLatest() {
    setBusy(true)
    setError(null)
    try {
      const { game, existing_game_id: existing } = await deps.api.latestGame()
      const where = PLATFORM_LABEL[game.platform]
      if (existing) {
        show(`Your latest ${where} game, vs ${opponent(game)}, is already here.`, 'info')
        navigate(`/games/${existing}`)
        return
      }
      if (game.pgn === null || game.error) {
        setError(`Your latest ${where} game can't be analyzed: ${game.error?.message ?? 'it has no moves.'}`)
        return
      }
      if (game.user_color === null) {
        setError(
          `Your username isn't in your latest ${where} game (${game.white} vs ${game.black}). ` +
            'Paste it below and choose your color.',
        )
        return
      }
      const external = { platform: game.platform, external_id: game.external_id }
      const run = await runAnalysis(deps, { pgn: game.pgn, user_color: game.user_color, external }, setStatus)
      const state: FreshAnalysis = { run }
      navigate(`/games/${run.game.game_id}`, { state })
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else if (caught instanceof ApiError && caught.status < 500) setError(errorText(caught))
      else show(errorText(caught), 'error')
      setStatus(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <FeatureCard as="section" className="latest-game" aria-labelledby="latest-game-title">
      <div className="latest-game-text">
        <h2 id="latest-game-title" className="latest-game-title">
          Just played a game?
        </h2>
        {linked.length > 0 ? (
          <p className="latest-game-lead">
            Analyze your latest game from{' '}
            {linked.map((p) => `${PLATFORM_LABEL[p]} (${usernameOf(settings, p)})`).join(' or ')}
            {linked.length > 1 ? ', whichever you played last' : ''}.
          </p>
        ) : (
          <p className="latest-game-lead">
            <Link to="/profile">Add your Chess.com or Lichess username</Link> and your latest game is one click away.
          </p>
        )}
      </div>
      {linked.length > 0 && (
        <Button className="latest-game-button" disabled={busy} onClick={() => void analyzeLatest()}>
          Analyze my latest game
        </Button>
      )}
      {status && (
        <ProgressBar label={statusLabel(status)} {...(status.phase === 'starting' ? { done: 0, total: 1 } : status)} />
      )}
      {error && (
        <p className="form-error latest-game-error" role="alert">
          {error}
        </p>
      )}
    </FeatureCard>
  )
}

function usernameOf(settings: { chesscom_username: string; lichess_username: string }, platform: Platform): string {
  return platform === 'chesscom' ? settings.chesscom_username : settings.lichess_username
}

function opponent(game: ImportRow): string {
  return (game.user_color === 'black' ? game.white : game.black) ?? 'your opponent'
}
