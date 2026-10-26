import type { AnalysisRun } from '../analysis/pipeline'
import type { EngineResult } from '../api/types'
import { formatEval, positionLabel } from '../engine/format'

interface EngineStatsProps {
  run: AnalysisRun
}

/** Engine diagnostics: depth and time per search (the M2 checkpoint evidence). */
export function EngineStats({ run }: EngineStatsProps) {
  const totalPlies = run.game.positions.length
  const rows = [...run.scan, ...run.verify]
  return (
    <details className="engine-stats">
      <summary>
        Engine details: {run.engine.build}, {run.engine.threads} thread(s) · scan{' '}
        {run.scan.length} positions in {seconds(run.scanMs)} · verify {run.verify.length} in{' '}
        {seconds(run.verifyMs)}
      </summary>
      <table data-testid="engine-results">
        <thead>
          <tr>
            <th scope="col">Tier</th>
            <th scope="col">Position</th>
            <th scope="col">Depth</th>
            <th scope="col">Time (ms)</th>
            <th scope="col">Eval</th>
            <th scope="col">Best line</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((result) => (
            <tr key={`${result.tier}-${result.fen}`} data-ply={result.ply ?? ''}>
              <td>{result.tier}</td>
              <td>{positionLabel(result.ply, totalPlies)}</td>
              <td>{result.depth}</td>
              <td>{result.time_ms}</td>
              <td>{formatEval(result.lines[0])}</td>
              <td className="line">{bestLine(result)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

function bestLine(result: EngineResult): string {
  return result.lines[0].moves_uci.join(' ')
}

function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}
