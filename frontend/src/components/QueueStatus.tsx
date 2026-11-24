import { useState } from 'react'
import { Link } from 'react-router'
import { useAnalysisQueue, useQueueState } from '../analysis/analysisQueueContext'
import { queueLabel } from '../analysis/queue'
import { Button } from '../ui'
import './QueueStatus.css'

/** Imported games being analyzed in the background (SPEC_V4 §8.2), shown on every page: the
 * player keeps using CoChess while it runs. After a run, a short summary until dismissed. */
export function QueueStatus() {
  const queue = useAnalysisQueue()
  const state = useQueueState(queue)
  const [dismissedRun, setDismissedRun] = useState<string | null>(null)

  if (state.running && state.progress) {
    return (
      <p className="queue-status" role="status">
        <strong>Analyzing your imported games.</strong> {queueLabel(state.progress)}. You can keep using CoChess
        meanwhile.
      </p>
    )
  }
  const done = state.finished.length
  const failed = state.failed.length
  const run = [...state.finished, ...state.failed].join()
  if (state.running || (done === 0 && failed === 0) || dismissedRun === run) return null
  const failedText =
    failed === 1
      ? "1 game couldn't be analyzed; open it from your games to try again. "
      : `${failed} games couldn't be analyzed; open them from your games to try again. `
  return (
    <p className="queue-status" role="status">
      {done > 0 && `Analyzed ${done} imported ${done === 1 ? 'game' : 'games'}. `}
      {failed > 0 && failedText}
      <Link to="/games">See your games</Link>{' '}
      <Button variant="link" className="queue-status-dismiss" onClick={() => setDismissedRun(run)}>
        Dismiss
      </Button>
    </p>
  )
}
