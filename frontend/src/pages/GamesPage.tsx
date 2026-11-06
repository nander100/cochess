import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { type AnalysisStatus, type PipelineDeps, runAnalysis, statusLabel } from '../analysis/pipeline'
import { ApiError, isLoggedOut } from '../api/client'
import type { CreateGameRequest, GameListItem, GameStatus, UserResult } from '../api/types'
import { GameInput } from '../components/GameInput'
import { DashboardView } from '../dashboard/DashboardView'
import { ImportPanel } from '../importing/ImportPanel'
import {
  ColorSwatch,
  EmptyState,
  ErrorState,
  Eyebrow,
  Pill,
  type PillTone,
  ProgressBar,
  Skeleton,
  Table,
  TintedPanel,
  useToast,
} from '../ui'
import type { FreshAnalysis } from './GamePage'
import './GamesPage.css'
import { errorText } from './util'

interface GamesPageProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

const RESULT: Record<UserResult, string> = { win: 'Won', loss: 'Lost', draw: 'Draw' }
const STATUS: Record<GameStatus, { text: string; tone: PillTone }> = {
  uploaded: { text: 'Not analyzed yet', tone: 'neutral' },
  scanned: { text: 'Analyzing…', tone: 'busy' },
  analyzed: { text: 'Analyzed', tone: 'analyzed' },
}
type Filter = 'all' | 'bullet' | 'blitz' | 'rapid' | 'classical'
const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'All time controls' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'classical', label: 'Classical' },
  { value: 'bullet', label: 'Bullet' },
]

/** The Games page and home (Main.dc.html): upload a game, the dashboard (SPEC_V3 §8.1), and all games. */
export function GamesPage({ deps, onLoggedOut }: GamesPageProps) {
  const { api } = deps
  const [games, setGames] = useState<GameListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0) // bumped when imported games arrive: the dashboard reloads

  const load = useCallback(
    () =>
      api.listGames().then(
        (list) => {
          setGames(list)
          setError(null)
        },
        (caught: unknown) => {
          if (isLoggedOut(caught)) onLoggedOut()
          else setError(errorText(caught))
        },
      ),
    [api, onLoggedOut],
  )

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="games-page">
      <section className="games-hero" aria-label="Upload a game">
        <div className="games-hero-text">
          <Eyebrow>Your games</Eyebrow>
          <h1 className="games-title">Upload a game. Learn one idea from it.</h1>
          <p className="games-lead">
            Stockfish checks every move in your browser. Your coach explains the turning points in plain language
            and turns them into short exercises.
          </p>
        </div>
        <Upload deps={deps} onLoggedOut={onLoggedOut} />
      </section>
      {error && <ErrorState message={`Your games couldn't be loaded. ${error}`} onRetry={() => void load()} />}
      {!error && games === null && <Skeleton lines={4} label="Loading games…" />}
      <ImportPanel
        deps={deps}
        onLoggedOut={onLoggedOut}
        onAdded={() => {
          void load()
          setVersion((n) => n + 1)
        }}
      />
      <DashboardView key={version} api={api} onLoggedOut={onLoggedOut} />
      {games !== null && <RecentGames games={games} />}
    </div>
  )
}

/** Paste a game, run the engine on it, then open it on the analysis board. */
function Upload({ deps, onLoggedOut }: GamesPageProps) {
  const navigate = useNavigate()
  const { show } = useToast()
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
      else if (aboutTheGame(caught)) setError(errorText(caught))
      else show(errorText(caught), 'error')
      setStatus(null)
    }
  }

  return (
    <TintedPanel className="games-upload">
      <GameInput disabled={status !== null} onSubmit={(request) => void analyze(request)} />
      {status && (
        <ProgressBar label={statusLabel(status)} {...(status.phase === 'starting' ? { done: 0, total: 1 } : status)} />
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </TintedPanel>
  )
}

/** A refusal about the pasted game (bad PGN, a duplicate): shown by the form, not as a toast. */
function aboutTheGame(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 422 || error.status === 409)
}

function RecentGames({ games }: { games: GameListItem[] }) {
  const [filter, setFilter] = useState<Filter>('all')
  const shown = filter === 'all' ? games : games.filter((game) => game.time_control_category === filter)
  return (
    <section className="games-recent" aria-labelledby="games-recent">
      <div className="games-recent-head">
        <h2 id="games-recent" className="games-section-title">
          All games
        </h2>
        {games.length > 0 && (
          <label className="games-filter">
            Show
            <select className="ui-input ui-select" value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
              {FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {games.length === 0 ? (
        <EmptyState title="No games yet">
          <p>Paste a game above, choose your color, and press Analyze game.</p>
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState title="No games in this time control">
          <p>Choose another time control above.</p>
        </EmptyState>
      ) : (
        <Table aria-label="All games">
          <thead>
            <tr>
              <th scope="col">Opponent</th>
              <th scope="col">Color</th>
              <th scope="col">Result</th>
              <th scope="col">Time control</th>
              <th scope="col">Accuracy</th>
              <th scope="col">Status</th>
              <th scope="col">
                <span className="visually-hidden">Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((game) => (
              <tr key={game.id}>
                <td className="games-opponent">{game.opponent}</td>
                <td>
                  <span className="games-color">
                    <ColorSwatch color={game.user_color} />
                    {game.user_color === 'white' ? 'White' : 'Black'}
                  </span>
                </td>
                <td>{game.user_result ? RESULT[game.user_result] : '–'}</td>
                <td className="games-muted">{game.time_control ?? '–'}</td>
                <td className="numeric">{game.accuracy === null ? '–' : `${game.accuracy}%`}</td>
                <td>
                  <Pill tone={STATUS[game.status].tone}>{STATUS[game.status].text}</Pill>
                </td>
                <td className="games-open">
                  <Link to={`/games/${game.id}`} aria-label={`Open the game vs ${game.opponent}`}>
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  )
}
