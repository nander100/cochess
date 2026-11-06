// Server-sent events over fetch (EventSource can't POST). Coach endpoints always stream SSE.

import type { Annotation, AnnotationColor } from './types'

export type CoachEvent =
  | { type: 'status'; message: string }
  | { type: 'text'; text: string }
  | { type: 'done'; invalid_moves_removed: string[] }
  | { type: 'error'; message: string }
  | { type: 'engine_request'; request_id: string; positions: EnginePositionRequest[] }
  /** A critical-moment attempt's grade and the moment's new state, before the coach's text. */
  | { type: 'moment'; grade: string | null; state: string }
  /** One checked board tag of the reply (SPEC_V3 §11.1), sent after the text. */
  | { type: 'annotation'; annotation: Annotation }

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
    case 'annotation': {
      const annotation = toAnnotation(record)
      return annotation ? { type: 'annotation', annotation } : null
    }
    default:
      return null
  }
}

const SQUARE = /^[a-h][1-8]$/
const COLORS: readonly string[] = ['green', 'red', 'yellow', 'blue']

function isColor(value: unknown): value is AnnotationColor {
  return typeof value === 'string' && COLORS.includes(value)
}

/** The backend has checked every shape; this only keeps out anything malformed. */
function toAnnotation(record: Record<string, unknown>): Annotation | null {
  const { tag_index, char_offset, arrows, squares } = record
  if (typeof tag_index !== 'number' || typeof char_offset !== 'number') return null
  if (!Array.isArray(arrows) || !Array.isArray(squares)) return null
  const okArrows = arrows.filter((a): a is Annotation['arrows'][number] => {
    const { orig, dest, color } = (a ?? {}) as Record<string, unknown>
    return typeof orig === 'string' && SQUARE.test(orig) && typeof dest === 'string' && SQUARE.test(dest) && isColor(color)
  })
  const okSquares = squares.filter((s): s is Annotation['squares'][number] => {
    const { square, color } = (s ?? {}) as Record<string, unknown>
    return typeof square === 'string' && SQUARE.test(square) && isColor(color)
  })
  return { tag_index, char_offset, arrows: okArrows, squares: okSquares }
}

function isPosition(value: unknown): value is EnginePositionRequest {
  if (typeof value !== 'object' || value === null) return false
  const { fen, label } = value as Record<string, unknown>
  return typeof fen === 'string' && (label === 'position' || label === 'after_candidate')
}
