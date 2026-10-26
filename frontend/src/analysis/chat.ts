import type { ApiClient } from '../api/client'
import type { CoachEvent, EnginePositionRequest } from '../api/sse'
import type { EngineResult } from '../api/types'

export type ChatProgress = 'writing' | 'thinking'

export interface ChatDeps {
  api: ApiClient
  /** Run the deep-dive tier on the positions the coach asked about. */
  analyzeDeep(positions: EnginePositionRequest[]): Promise<EngineResult[]>
}

/**
 * Ask the coach one question (SPEC §8.3). If the coach wants an engine analysis, run it here in
 * the browser and send the results back, until the coach answers in text. Throws with a
 * readable message if the coach or the engine fails.
 */
export async function askCoach(
  deps: ChatDeps,
  gameId: string,
  message: string,
  onProgress: (progress: ChatProgress) => void,
): Promise<string> {
  onProgress('writing')
  let outcome = await collect((onEvent) => deps.api.sendChat(gameId, message, onEvent))
  while (outcome.kind === 'engine') {
    const { requestId, positions } = outcome
    onProgress('thinking')
    const results = await deps.analyzeDeep(positions)
    onProgress('writing')
    outcome = await collect((onEvent) =>
      deps.api.submitEngineResult(gameId, requestId, results, onEvent),
    )
  }
  return outcome.text
}

type Outcome =
  | { kind: 'text'; text: string }
  | { kind: 'engine'; requestId: string; positions: EnginePositionRequest[] }

async function collect(
  run: (onEvent: (event: CoachEvent) => void) => Promise<void>,
): Promise<Outcome> {
  const state: { text: string; outcome: Outcome | null; error: string | null } = {
    text: '',
    outcome: null,
    error: null,
  }
  await run((event) => {
    if (event.type === 'text') state.text += event.text
    else if (event.type === 'done') state.outcome = { kind: 'text', text: state.text }
    else if (event.type === 'error') state.error = event.message
    else if (event.type === 'engine_request') {
      state.outcome = { kind: 'engine', requestId: event.request_id, positions: event.positions }
    }
  })
  if (state.error !== null) throw new Error(state.error)
  if (state.outcome === null) throw new Error('The connection to the coach was lost.')
  return state.outcome
}
