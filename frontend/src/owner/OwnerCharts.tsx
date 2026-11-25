import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { OwnerOverview, PlayerDetail } from '../api/ownerTypes'
import { SERIES, useTokenColors } from '../dashboard/chartColors'
import { MICROUSD, dollars, taskLabel } from './format'

// Loaded on demand (React.lazy), like the v3 dashboard's charts: Recharts stays out of the main
// bundle. Colors come from the chart tokens; the numbers are also shown as text beside each chart.
// No animation: the numbers are the point, and it respects reduced motion for free.

const INK = ['--color-fg', '--color-muted', '--color-border', '--color-bg'] as const
const HEIGHT = 260
const MARGIN = { top: 8, right: 16, bottom: 8, left: 8 }

function useInk() {
  const ink = useTokenColors(INK)
  const series = useTokenColors(SERIES)
  return {
    ink,
    color: (index: number) => series[SERIES[index % SERIES.length]],
    axis: { tick: { fill: ink['--color-muted'] }, stroke: ink['--color-border'] },
    tooltip: { background: ink['--color-bg'], borderColor: ink['--color-border'], color: ink['--color-fg'] },
  }
}

const asDollars = (value: unknown) => (typeof value === 'number' ? dollars(value * MICROUSD) : String(value))
const shortDay = (iso: string, monthly: boolean) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: 'UTC',
    ...(monthly ? { month: 'short', year: '2-digit' } : { month: 'short', day: 'numeric' }),
  })

/** Revenue next to API cost, per day (per month for all time). */
export function MoneyChart({ overview }: { overview: OwnerOverview }) {
  const { color, axis, tooltip, ink } = useInk()
  const monthly = overview.period === 'all'
  const data = overview.series.map((point) => ({
    label: shortDay(point.day, monthly),
    Revenue: point.revenue_microusd / MICROUSD,
    'API cost': point.api_cost_microusd / MICROUSD,
  }))
  return (
    <figure className="owner-chart" aria-label={`Revenue and API cost per ${monthly ? 'month' : 'day'}`}>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <BarChart data={data} margin={MARGIN} barGap={2}>
          <CartesianGrid stroke={ink['--color-border']} vertical={false} />
          <XAxis dataKey="label" {...axis} minTickGap={16} />
          <YAxis {...axis} width={56} tickFormatter={(v: number) => `$${v}`} />
          <Tooltip contentStyle={tooltip} formatter={asDollars} cursor={{ fill: ink['--color-border'] }} />
          <Legend wrapperStyle={{ color: ink['--color-fg'] }} />
          <Bar isAnimationActive={false} dataKey="Revenue" fill={color(0)} radius={[3, 3, 0, 0]} />
          <Bar isAnimationActive={false} dataKey="API cost" fill={color(1)} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

/** Coach calls per task in the period, largest first. */
export function TaskChart({ calls }: { calls: Record<string, number> }) {
  const { color, axis, tooltip, ink } = useInk()
  const data = Object.entries(calls)
    .sort(([, a], [, b]) => b - a)
    .map(([task, count]) => ({ task: taskLabel(task), Calls: count }))
  return (
    <figure className="owner-chart" aria-label="Coach calls per task">
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 34 + 24)}>
        <BarChart data={data} layout="vertical" margin={MARGIN}>
          <CartesianGrid stroke={ink['--color-border']} horizontal={false} />
          <XAxis type="number" {...axis} allowDecimals={false} />
          <YAxis type="category" dataKey="task" {...axis} width={128} />
          <Tooltip contentStyle={tooltip} cursor={{ fill: ink['--color-border'] }} />
          <Bar isAnimationActive={false} dataKey="Calls" fill={color(2)} radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

/** One player's API cost per week, stacked by task (the last 12 weeks). */
export function WeeklyCostChart({ weeks }: { weeks: PlayerDetail['cost_by_week'] }) {
  const { color, axis, tooltip, ink } = useInk()
  const tasks = [...new Set(weeks.flatMap((week) => Object.keys(week.by_task)))].sort()
  const data = weeks.map((week) => ({
    label: shortDay(week.week, false),
    ...Object.fromEntries(tasks.map((task) => [taskLabel(task), (week.by_task[task] ?? 0) / MICROUSD])),
  }))
  return (
    <figure className="owner-chart" aria-label="API cost per week, by task">
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <BarChart data={data} margin={MARGIN}>
          <CartesianGrid stroke={ink['--color-border']} vertical={false} />
          <XAxis dataKey="label" {...axis} />
          <YAxis {...axis} width={56} tickFormatter={(v: number) => `$${v}`} />
          <Tooltip contentStyle={tooltip} formatter={asDollars} cursor={{ fill: ink['--color-border'] }} />
          <Legend wrapperStyle={{ color: ink['--color-fg'] }} />
          {tasks.map((task, index) => (
            <Bar isAnimationActive={false} key={task} dataKey={taskLabel(task)} stackId="cost" fill={color(index)} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}
