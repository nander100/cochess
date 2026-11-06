import { useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Color, Dashboard, UserResult } from '../api/types'
import { SERIES, useTokenColors } from './chartColors'

// Loaded on demand (React.lazy): Recharts stays out of the main bundle.

const INK = ['--color-fg', '--color-muted', '--color-border', '--color-bg', '--chess-good', '--chess-blunder'] as const
const CHART_HEIGHT = 240
const MARKER = 8 // px: the smallest a dot can be and still be hit
const RESULTS = ['win', 'loss', 'draw'] as const
const RESULT_LABEL: Record<UserResult, string> = { win: 'Win', loss: 'Loss', draw: 'Draw' }
const SHAPE: Record<UserResult, 'circle' | 'cross' | 'square'> = { win: 'circle', loss: 'cross', draw: 'square' }

interface MistakeChartProps {
  trend: Dashboard['mistake_trend']
}

/** Mistake types over time (SPEC_V3 §8.1): the weighted rate per game of the top 5 themes after
 * each analyzed game. Each line is labeled at its end, and the legend hides or shows a theme. */
export function MistakeChart({ trend }: MistakeChartProps) {
  const series = useTokenColors(SERIES)
  const ink = useTokenColors(INK)
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set())
  const data = trend.points.map((p) => ({ games: p.games_analyzed, ...p.rates }))
  // A theme keeps its color whatever is hidden: color follows the theme, not its place.
  const color = (index: number) => series[SERIES[index]]
  function toggle(theme: string) {
    setHidden((was) => {
      const next = new Set(was)
      if (next.has(theme)) next.delete(theme)
      else next.add(theme)
      return next
    })
  }
  return (
    <figure className="dashboard-chart" aria-label="Mistake types over time">
      <div className="dashboard-legend" role="group" aria-label="Show or hide a mistake type">
        {trend.themes.map((theme, index) => (
          <button
            key={theme.theme}
            type="button"
            className="dashboard-legend-item"
            aria-pressed={!hidden.has(theme.theme)}
            onClick={() => toggle(theme.theme)}
          >
            <span className="dashboard-swatch" style={{ background: color(index) }} aria-hidden="true" />
            {theme.label}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data} margin={{ top: 8, right: 120, bottom: 16, left: 0 }}>
          <CartesianGrid stroke={ink['--color-border']} vertical={false} />
          <XAxis
            dataKey="games"
            type="number"
            domain={['dataMin', 'dataMax']}
            allowDecimals={false}
            tick={{ fill: ink['--color-muted'] }}
            stroke={ink['--color-border']}
            label={{ value: 'Games analyzed', position: 'insideBottom', offset: -12, fill: ink['--color-muted'] }}
          />
          <YAxis tick={{ fill: ink['--color-muted'] }} stroke={ink['--color-border']} width={40} />
          <Tooltip
            contentStyle={{ background: ink['--color-bg'], borderColor: ink['--color-border'], color: ink['--color-fg'] }}
            labelFormatter={(games) => `After ${String(games)} games`}
            formatter={(value) => (typeof value === 'number' ? value.toFixed(2) : String(value))}
          />
          {trend.themes.map((theme, index) =>
            hidden.has(theme.theme) ? null : (
              <Line
                key={theme.theme}
                type="monotone"
                dataKey={theme.theme}
                name={theme.label}
                stroke={color(index)}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: MARKER / 2 }}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey={theme.theme}
                  content={(props) => {
                    const { x, y, index: at } = props as { x?: number | string; y?: number | string; index?: number }
                    if (at !== data.length - 1 || x === undefined || y === undefined) return null
                    return (
                      <text x={Number(x) + 6} y={Number(y)} dy={4} fill={ink['--color-fg']} fontSize={12}>
                        {theme.label}
                      </text>
                    )
                  }}
                />
              </Line>
            ),
          )}
        </LineChart>
      </ResponsiveContainer>
      <figcaption className="dashboard-caption">
        Mistakes per game, recent games counting most, after each analyzed game.
      </figcaption>
    </figure>
  )
}

interface AccuracyChartProps {
  accuracy: Dashboard['accuracy']
}

/** Accuracy trend (SPEC_V3 §8.1): one dot per game, marked by its result (shape and color, named
 * in the key), the average of the last 10 games, and accuracy by phase. */
export function AccuracyChart({ accuracy }: AccuracyChartProps) {
  const ink = useTokenColors(INK)
  const [side, setSide] = useState<Color | 'both'>('both')
  const data = accuracy.points
    .filter((p) => side === 'both' || p.color === side)
    .map((p, index) => ({ ...p, game: index + 1 }))
  const fill: Record<UserResult, string> = {
    win: ink['--chess-good'],
    loss: ink['--chess-blunder'],
    draw: ink['--color-muted'],
  }
  return (
    <figure className="dashboard-chart" aria-label="Accuracy trend">
      <div className="dashboard-legend" role="group" aria-label="Which games">
        {(['both', 'white', 'black'] as const).map((value) => (
          <button
            key={value}
            type="button"
            className="dashboard-legend-item"
            aria-pressed={side === value}
            onClick={() => setSide(value)}
          >
            {value === 'both' ? 'Both colors' : value === 'white' ? 'As White' : 'As Black'}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={ink['--color-border']} vertical={false} />
          <XAxis
            dataKey="game"
            type="number"
            domain={[1, Math.max(1, data.length)]}
            allowDecimals={false}
            tick={{ fill: ink['--color-muted'] }}
            stroke={ink['--color-border']}
          />
          <YAxis domain={[0, 100]} tick={{ fill: ink['--color-muted'] }} stroke={ink['--color-border']} width={40} />
          <Tooltip
            contentStyle={{ background: ink['--color-bg'], borderColor: ink['--color-border'], color: ink['--color-fg'] }}
            labelFormatter={(game) => `Game ${String(game)}`}
            formatter={(value, name) => [`${String(value)}%`, String(name)]}
          />
          {RESULTS.map((result) => (
            <Scatter
              key={result}
              name={RESULT_LABEL[result]}
              data={data.filter((d) => d.result === result)}
              dataKey="accuracy"
              fill={fill[result]}
              shape={SHAPE[result]}
              isAnimationActive={false}
            />
          ))}
          <Line
            dataKey="rolling"
            name="Average of the last 10"
            stroke={ink['--color-fg']}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <ul className="dashboard-key" aria-label="Key">
        {RESULTS.map((result) => (
          <li key={result}>
            <span className={`dashboard-marker dashboard-marker-${result}`} aria-hidden="true" />
            {RESULT_LABEL[result]}
          </li>
        ))}
        <li>
          <span className="dashboard-marker dashboard-marker-line" aria-hidden="true" />
          Average of the last 10 games
        </li>
      </ul>
      <PhaseBars byPhase={accuracy.by_phase} />
    </figure>
  )
}

const PHASES = [
  ['opening', 'Opening'],
  ['middlegame', 'Middlegame'],
  ['endgame', 'Endgame'],
] as const

function PhaseBars({ byPhase }: { byPhase: Dashboard['accuracy']['by_phase'] }) {
  return (
    <dl className="dashboard-phases">
      {PHASES.map(([key, label]) => {
        const value = byPhase[key]
        return (
          <div key={key} className="dashboard-phase">
            <dt>{label}</dt>
            <dd>
              <span className="dashboard-phase-track" aria-hidden="true">
                <span className="dashboard-phase-bar" style={{ width: `${value ?? 0}%` }} />
              </span>
              {value === null ? 'No games yet' : `${value}%`}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}
