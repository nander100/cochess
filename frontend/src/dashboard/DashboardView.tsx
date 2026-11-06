import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Color, Dashboard, DashboardFilters, DashboardRange, FocusArea, TimeControl, UserResult } from '../api/types'
import { errorText } from '../pages/util'
import { Card, ColorSwatch, EmptyState, ErrorState, FeatureCard, Pill, type PillTone, Skeleton, Table } from '../ui'
import '../components/CoachText.css'
import './DashboardView.css'

const MistakeChart = lazy(() => import('./DashboardCharts').then((m) => ({ default: m.MistakeChart })))
const AccuracyChart = lazy(() => import('./DashboardCharts').then((m) => ({ default: m.AccuracyChart })))

const RESULT: Record<UserResult, string> = { win: 'Won', loss: 'Lost', draw: 'Draw' }
const TREND: Record<NonNullable<FocusArea['trend']>, { text: string; tone: PillTone }> = {
  improving: { text: '↓ Improving', tone: 'good' },
  worsening: { text: '↑ Getting worse', tone: 'blunder' },
  steady: { text: '→ Steady', tone: 'neutral' },
}
const TIME_CONTROLS: { value: TimeControl | ''; label: string }[] = [
  { value: '', label: 'All time controls' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'classical', label: 'Classical' },
  { value: 'bullet', label: 'Bullet' },
]
const RANGES: { value: DashboardRange; label: string }[] = [
  { value: '10', label: 'Last 10 games' },
  { value: '25', label: 'Last 25 games' },
  { value: 'all', label: 'All games' },
]

interface DashboardViewProps {
  api: ApiClient
  onLoggedOut: () => void
}

/** The dashboard (SPEC_V3 §8.1), on the Games page under the upload form (docs/design/screens.md):
 * focus areas, games to continue, the two trends, recent games, and the assessment. */
export function DashboardView({ api, onLoggedOut }: DashboardViewProps) {
  const [filters, setFilters] = useState<DashboardFilters>({ tc: null, color: null, range: 'all' })
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.dashboard(filters).then(
      (dashboard) => {
        setData(dashboard)
        setError(null)
      },
      (caught: unknown) => {
        if (isLoggedOut(caught)) onLoggedOut()
        else setError(errorText(caught))
      },
    )
  }, [api, filters, onLoggedOut])

  useEffect(load, [load])

  return (
    <section className="dashboard" aria-labelledby="dashboard-title">
      <div className="dashboard-head">
        <h2 id="dashboard-title" className="games-section-title">
          Your progress
        </h2>
        <Filters filters={filters} onChange={setFilters} />
      </div>
      {error && <ErrorState message={`Your progress couldn't be loaded. ${error}`} onRetry={load} />}
      {!error && data === null && <Skeleton lines={4} label="Loading your progress…" />}
      {data && <Sections data={data} />}
    </section>
  )
}

function Filters({ filters, onChange }: { filters: DashboardFilters; onChange: (f: DashboardFilters) => void }) {
  return (
    <div className="dashboard-filters">
      <label className="games-filter">
        <span className="visually-hidden">Time control</span>
        <select
          className="ui-input ui-select"
          value={filters.tc ?? ''}
          onChange={(e) => onChange({ ...filters, tc: (e.target.value || null) as TimeControl | null })}
        >
          {TIME_CONTROLS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="games-filter">
        <span className="visually-hidden">Color</span>
        <select
          className="ui-input ui-select"
          value={filters.color ?? ''}
          onChange={(e) => onChange({ ...filters, color: (e.target.value || null) as Color | null })}
        >
          <option value="">Both colors</option>
          <option value="white">As White</option>
          <option value="black">As Black</option>
        </select>
      </label>
      <label className="games-filter">
        <span className="visually-hidden">Range</span>
        <select
          className="ui-input ui-select"
          value={filters.range}
          onChange={(e) => onChange({ ...filters, range: e.target.value as DashboardRange })}
        >
          {RANGES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

function Sections({ data }: { data: Dashboard }) {
  const nothing = data.games === 0 && data.focus_areas.length === 0
  return (
    <>
      {nothing && (
        <EmptyState title="Nothing to show yet">
          <p>
            Analyze a game or <Link to="/onboarding">start your 12-game assessment</Link> to see your trends.
          </p>
        </EmptyState>
      )}
      {data.focus_areas.length > 0 && <FocusAreas areas={data.focus_areas} />}
      {data.continue_games.length > 0 && <ContinueGames games={data.continue_games} />}
      {data.games > 0 && (
        <div className="dashboard-charts">
          <Suspense fallback={<Skeleton lines={3} label="Loading charts…" />}>
            {data.mistake_trend.points.length > 1 && (
              <Card as="section" aria-labelledby="dashboard-mistakes">
                <h3 id="dashboard-mistakes" className="dashboard-subtitle">
                  Mistake types over time
                </h3>
                <p className="dashboard-note">Across all your games.</p>
                <MistakeChart trend={data.mistake_trend} />
              </Card>
            )}
            <Card as="section" aria-labelledby="dashboard-accuracy">
              <h3 id="dashboard-accuracy" className="dashboard-subtitle">
                Accuracy trend
              </h3>
              <AccuracyChart accuracy={data.accuracy} />
            </Card>
          </Suspense>
        </div>
      )}
      {data.recent.length > 0 && <RecentGames games={data.recent} />}
      <Assessment card={data.onboarding} />
    </>
  )
}

function FocusAreas({ areas }: { areas: FocusArea[] }) {
  return (
    <section aria-labelledby="dashboard-focus">
      <h3 id="dashboard-focus" className="dashboard-subtitle">
        Focus areas
      </h3>
      <p className="dashboard-note">From all your analyzed games.</p>
      <div className="dashboard-focus">
        {areas.map((area, index) => {
          const Box = index === 0 ? FeatureCard : Card
          const example = area.example_ply ? `?ply=${area.example_ply}` : ''
          return (
            <Box key={area.theme} as="article" className="dashboard-focus-card" aria-label={area.label}>
              <span className="ui-card-value">{area.label}</span>
              <span className="dashboard-focus-meta">
                {area.trend && <Pill tone={TREND[area.trend].tone}>{TREND[area.trend].text}</Pill>}
                <span>
                  {area.rate_per_game.toFixed(1)} per game · seen in {area.games_seen} games
                </span>
              </span>
              {area.example_game_id && (
                <Link className="games-link" to={`/games/${area.example_game_id}${example}`}>
                  See an example{area.example_move ? ` (${area.example_move})` : ''} →
                </Link>
              )}
              {area.puzzles.length > 0 && (
                <span className="dashboard-puzzles" aria-label="Practice on Lichess">
                  {area.puzzles.map((p) => (
                    <a key={p.theme} className="coach-puzzle" href={p.url} target="_blank" rel="noopener noreferrer">
                      {p.label}
                    </a>
                  ))}
                </span>
              )}
            </Box>
          )
        })}
      </div>
    </section>
  )
}

function ContinueGames({ games }: { games: Dashboard['continue_games'] }) {
  return (
    <section aria-labelledby="dashboard-continue">
      <h3 id="dashboard-continue" className="dashboard-subtitle">
        Continue where you left off
      </h3>
      <ul className="dashboard-continue">
        {games.map((game) => (
          <li key={game.game_id}>
            <Link to={`/games/${game.game_id}?view=moments`} className="dashboard-continue-link">
              <span>vs {game.opponent}</span>
              <span className="games-muted">
                {game.moments_done} of {game.moments_total} critical moments done
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function RecentGames({ games }: { games: Dashboard['recent'] }) {
  return (
    <section aria-labelledby="dashboard-recent">
      <h3 id="dashboard-recent" className="dashboard-subtitle">
        Recent games
      </h3>
      <Table aria-label="Recent analyzed games">
        <thead>
          <tr>
            <th scope="col">Opponent</th>
            <th scope="col">Color</th>
            <th scope="col">Result</th>
            <th scope="col">Accuracy</th>
            <th scope="col">Critical moments</th>
          </tr>
        </thead>
        <tbody>
          {games.map((game) => (
            <tr key={game.game_id}>
              <td className="games-opponent">
                <Link to={`/games/${game.game_id}`}>{game.opponent}</Link>
              </td>
              <td>
                <span className="games-color">
                  <ColorSwatch color={game.color} />
                  {game.color === 'white' ? 'White' : 'Black'}
                </span>
              </td>
              <td>{game.result ? RESULT[game.result] : '–'}</td>
              <td className="numeric">{game.accuracy === null ? '–' : `${game.accuracy}%`}</td>
              <td className="numeric">
                {game.moments_total === 0 ? '–' : `${game.moments_done}/${game.moments_total}`}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </section>
  )
}

function Assessment({ card }: { card: Dashboard['onboarding'] }) {
  return (
    <Card as="section" className="dashboard-assessment" aria-labelledby="dashboard-assessment">
      <h3 id="dashboard-assessment" className="dashboard-subtitle">
        {card.complete ? 'Your baseline report' : 'The 12-game assessment'}
      </h3>
      {card.complete ? (
        <Link to="/onboarding" className="games-link">
          {card.has_report ? 'Read your baseline report →' : 'Write your baseline report →'}
        </Link>
      ) : (
        <>
          <p className="dashboard-note">
            {card.analyzed} of {card.total} games analyzed. The assessment gives your coach a baseline to work from.
          </p>
          <Link to="/onboarding" className="games-link">
            {card.analyzed > 0 ? 'Continue the assessment →' : 'Start the assessment →'}
          </Link>
        </>
      )}
    </Card>
  )
}
