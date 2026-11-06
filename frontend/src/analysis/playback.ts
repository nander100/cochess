import type { ApiClient } from '../api/client'
import type { EngineResult, LineLink, Playback } from '../api/types'
import { isGameOver } from '../engine/live'
import { positionsAlong } from './walkthrough'

export interface PlaybackDeps {
  api: ApiClient
  /** The scan tier on one position (SPEC_V3 §9.6 step 1). */
  scan(fen: string): Promise<EngineResult>
}

/**
 * Where a linked line's playback stops, and the caption there (SPEC_V3 §9.6): every position of
 * the line that can be searched is scanned here, then the backend decides. One request per
 * link: asking again for the same link reuses the first answer.
 */
export class Settler {
  private readonly answers = new Map<string, Promise<Playback>>()
  // Links are scanned one after another: the engine searches one position at a time.
  private queue: Promise<unknown> = Promise.resolve()

  private readonly deps: PlaybackDeps

  constructor(deps: PlaybackDeps) {
    this.deps = deps
  }

  settle(link: LineLink): Promise<Playback> {
    let answer = this.answers.get(link.line_id)
    if (!answer) {
      answer = this.queue.then(() => this.run(link))
      this.queue = answer.catch(() => undefined)
      answer.catch(() => this.answers.delete(link.line_id)) // let a later click retry
      this.answers.set(link.line_id, answer)
    }
    return answer
  }

  private async run(link: LineLink): Promise<Playback> {
    const fens = positionsAlong(link.start_path_uci, link.moves_uci).filter((fen) => !isGameOver(fen))
    const results: EngineResult[] = []
    for (const fen of fens) results.push(await this.deps.scan(fen))
    return this.deps.api.playback(link.line_id, results)
  }
}
