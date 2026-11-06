import { Chess } from 'chess.js'
import { ApiError, type ApiClient } from '../api/client'
import type { CoachEvent } from '../api/sse'
import type { EngineResult, Walkthrough, WalkthroughRequest } from '../api/types'
import { isGameOver } from '../engine/live'

/** The most moves a walkthrough covers (mirrors backend CoachSettings.walkthrough_max_plies). */
export const WALK_MAX_PLIES = 10
const NEEDS_SCAN = 428 // the backend has no walkthrough of this line yet: analyze it first

/** scanning: the engine checks each position of the line; writing: the coach is answering. */
export type WalkthroughProgress = { kind: 'scanning'; done: number; total: number } | { kind: 'writing' }

export interface WalkthroughDeps {
  api: ApiClient
  /** The verify tier on one position: SPEC_V3 §7.2 step 2 says scan, but its shallow evals
   * misled the coach (owner decision at M4, PLAN_V3). */
  search(fen: string): Promise<EngineResult>
}

/**
 * Walk through `line` from `startPath` (SPEC_V3 §7.2). A line walked before comes straight from
 * the backend's cache; otherwise every position along it that can be searched is analyzed here
 * (verify tier), with progress, and sent with the request.
 */
export async function walkThrough(
  deps: WalkthroughDeps,
  gameId: string,
  startPath: readonly string[],
  line: readonly string[],
  onProgress: (progress: WalkthroughProgress) => void,
): Promise<Walkthrough> {
  const body: WalkthroughRequest = { start_path_uci: [...startPath], line_uci: [...line], step_results: [] }
  onProgress({ kind: 'writing' })
  try {
    return await request(deps.api, gameId, body)
  } catch (error) {
    if (!(error instanceof ApiError && error.status === NEEDS_SCAN)) throw error
  }
  const fens = positionsAlong(startPath, line).filter((fen) => !isGameOver(fen))
  const results: EngineResult[] = []
  for (const [done, fen] of fens.entries()) {
    onProgress({ kind: 'scanning', done, total: fens.length })
    results.push(await deps.search(fen))
  }
  onProgress({ kind: 'writing' })
  return request(deps.api, gameId, { ...body, step_results: results })
}

/** The start position and the position after each move of the line. */
export function positionsAlong(startPath: readonly string[], line: readonly string[]): string[] {
  const board = new Chess()
  for (const uci of startPath) board.move(toMove(uci))
  const fens = [board.fen()]
  for (const uci of line) {
    board.move(toMove(uci))
    fens.push(board.fen())
  }
  return fens
}

function toMove(uci: string) {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] }
}

async function request(api: ApiClient, gameId: string, body: WalkthroughRequest): Promise<Walkthrough> {
  const state: { walkthrough: Walkthrough | null; error: string | null } = { walkthrough: null, error: null }
  await api.walkthrough(gameId, body, (event: CoachEvent) => {
    if (event.type === 'walkthrough') state.walkthrough = event.walkthrough
    else if (event.type === 'error') state.error = event.message
  })
  if (state.error !== null) throw new Error(state.error)
  if (state.walkthrough === null) throw new Error('The connection to the coach was lost.')
  return state.walkthrough
}
