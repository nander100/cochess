import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { GameListItem, GameStatus, UserResult } from '../api/types'
import { errorText, gameDate } from './util'

interface GamesPageProps {
  api: ApiClient
  onLoggedOut: () => void
}

const RESULT: Record<UserResult, string> = { win: 'Won', loss: 'Lost', draw: 'Draw' }
const STATUS: Record<GameStatus, string> = {
  uploaded: 'Not analyzed yet',
  scanned: 'Analysis unfinished',
  analyzed: 'Analyzed',
}

/** My games (SPEC_V2 §11): most recently played first; each opens on the analysis board. */
export function GamesPage({ api, onLoggedOut }: GamesPageProps) {
  const [games, setGames] = useState<GameListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listGames().then(setGames, (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    })
  }, [api, onLoggedOut])

  if (error) {
    return (
      <p className="run-error" role="alert">
        {error}
      </p>
    )
  }
  if (games === null) return <p className="coach-writing">Loading your games…</p>
  if (games.length === 0) {
    return (
      <section className="panel games-empty">
        <h2>My games</h2>
        <p>
          No games yet. <Link to="/new">Analyze your first game</Link>.
        </p>
      </section>
    )
  }
  return (
    <section className="panel" aria-label="My games">
      <div className="games-header">
        <h2>My games</h2>
        <Link to="/new" className="button-link">
          Analyze a game
        </Link>
      </div>
      <table className="games">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Opponent</th>
            <th scope="col">You</th>
            <th scope="col">Result</th>
            <th scope="col">Time control</th>
            <th scope="col">Accuracy</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {games.map((game) => (
            <tr key={game.id}>
              <td>
                <Link to={`/games/${game.id}`}>
                  {gameDate(game.played_at)}
                </Link>
              </td>
              <td>{game.opponent}</td>
              <td>{game.user_color === 'white' ? 'White' : 'Black'}</td>
              <td className={game.user_result ?? ''}>{game.user_result ? RESULT[game.user_result] : '–'}</td>
              <td>{game.time_control ?? '–'}</td>
              <td>{game.accuracy === null ? '–' : `${game.accuracy}%`}</td>
              <td>{STATUS[game.status]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
