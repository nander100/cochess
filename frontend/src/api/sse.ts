// Server-sent events over fetch (EventSource can't POST). Coach endpoints always stream SSE.

export type CoachEvent =
  | { type: 'status'; message: string }
  | { type: 'text'; text: string }
  | { type: 'done'; invalid_moves_removed: string[] }
  | { type: 'error'; message: string }
  | { type: 'engine_request'; request_id: string; positions: EnginePositionRequest[] }
  /** A critical-moment attempt's grade and the moment's new state, before the coach's text. */
  | { type: 'moment'; grade: string | null; state: string }

/** A position the coach wants the deep-dive engine tier to analyze (SPEC §8.3). */
export interface EnginePositionRequest {
  fen: string
  label: 'position' | 'after_candidate'
}

/** Read an SSE response body, calling `onEvent` for each recognized event, until it ends. */
export async function readCoachEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: CoachEvent) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = done ? '' : (blocks.pop() ?? '')
    for (const block of blocks) {
      const event = parseBlock(block)
      if (event) onEvent(event)
    }
    if (done) return
  }
}

function parseBlock(block: string): CoachEvent | null {
  let name = ''
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice('event: '.length)
    else if (line.startsWith('data: ')) data += line.slice('data: '.length)
    // lines starting with ':' are keepalive comments
  }
  if (!name || !data) return null
  let payload: unknown
  try {
    payload = JSON.parse(data)
  } catch {
    return null
  }
  return toCoachEvent(name, payload)
}

function toCoachEvent(name: string, payload: unknown): CoachEvent | null {
  if (typeof payload !== 'object' || payload === null) return null
  const record = payload as Record<string, unknown>
  switch (name) {
    case 'status':
    case 'error':
      return typeof record.message === 'string' ? { type: name, message: record.message } : null
    case 'text':
      return typeof record.text === 'string' ? { type: 'text', text: record.text } : null
    case 'done': {
      const removed = Array.isArray(record.invalid_moves_removed)
        ? record.invalid_moves_removed.filter((m): m is string => typeof m === 'string')
        : []
      return { type: 'done', invalid_moves_removed: removed }
    }
    case 'engine_request': {
      const positions = Array.isArray(record.positions) ? record.positions.filter(isPosition) : []
      if (typeof record.request_id !== 'string' || positions.length === 0) return null
      return { type: 'engine_request', request_id: record.request_id, positions }
    }
    case 'moment':
      return typeof record.state === 'string'
        ? { type: 'moment', grade: typeof record.grade === 'string' ? record.grade : null, state: record.state }
        : null
    default:
      return null
  }
}

function isPosition(value: unknown): value is EnginePositionRequest {
  if (typeof value !== 'object' || value === null) return false
  const { fen, label } = value as Record<string, unknown>
  return typeof fen === 'string' && (label === 'position' || label === 'after_candidate')
}
