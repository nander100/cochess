import { Chess } from 'chess.js'
import type { ApiClient } from '../api/client'
import type { CoachEvent } from '../api/sse'
import type { EngineResult, MomentGrade, MomentState } from '../api/types'
import { isGameOver } from '../engine/live'

/** checking: the engine is analyzing the move; writing: the coach is answering. */
export type MomentProgress = 'checking' | 'writing'

export interface MomentDeps {
  api: ApiClient
  /** The deep-dive tier on one position (SPEC_V2 §8.2 step 4). */
  analyzeDeep(fen: string): Promise<EngineResult>
}

export interface MomentReply {
  text: string
  /** Set after an attempt: how the engine graded it, and the moment's new state. */
  grade: MomentGrade | null
  state: MomentState | null
}

/** The deep search of each moment's position, run once per moment and page visit (it's sent with
 * every attempt and "Show me"; the backend checks it and keeps the first). */
export class BeforeSearches {
  private readonly searches = new Map<number, Promise<EngineResult>>()

  get(deps: MomentDeps, index: number, fen: string): Promise<EngineResult> {
    let search = this.searches.get(index)
    if (!search) {
      search = deps.analyzeDeep(fen)
      search.catch(() => this.searches.delete(index)) // let a retry search again
      this.searches.set(index, search)
    }
    return search
  }
}

function play(fen: string, uci: string): { san: string; fen: string } | null {
  try {
    const chess = new Chess(fen)
    const promotion = uci.length > 4 ? { promotion: uci[4] } : {}
    const { san } = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), ...promotion })
    return { san, fen: chess.fen() }
  } catch {
    return null // chess.js throws on an illegal move
  }
}

/** Play `uci` in `fen`; null if it isn't legal there. */
export function fenAfter(fen: string, uci: string): string | null {
  return play(fen, uci)?.fen ?? null
}

/** The SAN of `uci` in `fen` ("Nf3"), or the UCI itself if it isn't legal there. */
export function sanOf(fen: string, uci: string): string {
  return play(fen, uci)?.san ?? uci
}

/** Check the player's move with the engine (before and after), then send it to be graded. */
export async function tryMove(
  deps: MomentDeps,
  searches: BeforeSearches,
  gameId: string,
  index: number,
  fen: string,
  uci: string,
  reasoning: string,
  onProgress: (progress: MomentProgress) => void,
): Promise<MomentReply> {
  const after = fenAfter(fen, uci)
  if (after === null) throw new Error("That move isn't legal in this position.")
  onProgress('checking')
  const before = await searches.get(deps, index, fen)
  const engineAfter = isGameOver(after) ? undefined : await deps.analyzeDeep(after)
  onProgress('writing')
  const body = {
    move_uci: uci,
    engine_before: before,
    ...(reasoning.trim() ? { reasoning: reasoning.trim() } : {}),
    ...(engineAfter ? { engine_after: engineAfter } : {}),
  }
  return collect((onEvent) => deps.api.momentAttempt(gameId, index, body, onEvent))
}

/** "Show me": reveal the answer (the backend needs the position's deep search for it). */
export async function showMe(
  deps: MomentDeps,
  searches: BeforeSearches,
  gameId: string,
  index: number,
  fen: string,
  onProgress: (progress: MomentProgress) => void,
): Promise<MomentReply> {
  onProgress('checking')
  const before = await searches.get(deps, index, fen)
  onProgress('writing')
  return collect((onEvent) => deps.api.momentReveal(gameId, index, before, onEvent))
}

/** Any other step (start, a question, the wrap-up): the coach's answer. */
export async function coachStep(
  run: (onEvent: (event: CoachEvent) => void) => Promise<void>,
  onProgress: (progress: MomentProgress) => void,
): Promise<MomentReply> {
  onProgress('writing')
  return collect(run)
}

async function collect(run: (onEvent: (event: CoachEvent) => void) => Promise<void>): Promise<MomentReply> {
  const reply: { text: string; done: boolean; error: string | null; grade: MomentGrade | null; state: MomentState | null } = {
    text: '',
    done: false,
    error: null,
    grade: null,
    state: null,
  }
  await run((event) => {
    if (event.type === 'text') reply.text += event.text
    else if (event.type === 'done') reply.done = true
    else if (event.type === 'error') reply.error = event.message
    else if (event.type === 'moment') {
      reply.grade = event.grade as MomentGrade | null
      reply.state = event.state as MomentState
    }
  })
  if (reply.error !== null) throw new Error(reply.error)
  if (!reply.done) throw new Error('The connection to the coach was lost.')
  return { text: reply.text, grade: reply.grade, state: reply.state }
}
