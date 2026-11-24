import { createContext, useContext, useSyncExternalStore } from 'react'
import type { AnalysisQueue, QueueState } from './backgroundQueue'

/** The tab's one background analysis queue (SPEC_V4 §8.2), made in App and shared by every page. */
export const AnalysisQueueContext = createContext<AnalysisQueue | null>(null)

export function useAnalysisQueue(): AnalysisQueue {
  const queue = useContext(AnalysisQueueContext)
  if (queue === null) throw new Error('useAnalysisQueue needs an AnalysisQueueContext provider')
  return queue
}

/** The queue's state, re-rendering as games are added, progress, and finish. */
export function useQueueState(queue: AnalysisQueue): QueueState {
  return useSyncExternalStore(
    (onChange) => queue.subscribe(onChange),
    () => queue.state,
  )
}
