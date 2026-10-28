import type { EngineConfig, OnboardingStatus } from '../api/types'
import { type AnalysisStatus, type PipelineDeps, resumeGame, statusLabel } from './pipeline'

/** Where the onboarding queue is: game `game` of `total`, and that game's analysis status. */
export interface QueueProgress {
  game: number
  total: number
  status: AnalysisStatus
}

/**
 * Analyze the onboarding games one after another (SPEC_V2 §10.3 step 4). The server keeps each
 * game's status, so this always starts from the first game not yet analyzed: closing the tab and
 * coming back continues where it stopped. Resolves with the final status.
 */
export async function runOnboardingQueue(
  deps: PipelineDeps,
  onProgress: (progress: QueueProgress) => void,
): Promise<OnboardingStatus> {
  let config: EngineConfig | null = null
  const tried = new Set<string>()
  for (;;) {
    const status = await deps.api.onboardingStatus()
    const index = status.games.findIndex((game) => game.status !== 'analyzed')
    if (index < 0) return status
    const next = status.games[index]
    // A game analyzed once and still not done would loop forever: stop and say so instead.
    if (tried.has(next.id)) throw new Error(`Game ${index + 1} couldn't be analyzed. Please try again.`)
    tried.add(next.id)
    config ??= await deps.api.engineConfig()
    const total = status.games.length
    onProgress({ game: index + 1, total, status: { phase: 'starting' } })
    const detail = await deps.api.getGame(next.id)
    await resumeGame(deps, detail, config, (game) => onProgress({ game: index + 1, total, status: game }))
  }
}

/** "Game 3 of 12 — move 14 of 38". */
export function queueLabel({ game, total, status }: QueueProgress): string {
  const prefix = `Game ${game} of ${total}`
  if (status.phase === 'scanning') return `${prefix} — move ${status.moveNumber} of ${status.totalMoves}`
  return `${prefix} — ${statusLabel(status).replace(/…$/, '').replace(/^./, (c) => c.toLowerCase())}`
}
