import { type CoachEvent, readCoachEvents } from './sse'

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
}

async function collect(...chunks: string[]): Promise<CoachEvent[]> {
  const events: CoachEvent[] = []
  await readCoachEvents(streamOf(...chunks), (event) => events.push(event))
  return events
}

test('parses each event type in order', async () => {
  const events = await collect(
    'event: status\ndata: {"message": "Coach is writing…"}\n\n',
    'event: text\ndata: {"text": "### Overall\\n"}\n\n',
    'event: text\ndata: {"text": "Good game."}\n\n',
    'event: done\ndata: {"invalid_moves_removed": ["Qh5"]}\n\n',
  )

  expect(events).toEqual([
    { type: 'status', message: 'Coach is writing…' },
    { type: 'text', text: '### Overall\n' },
    { type: 'text', text: 'Good game.' },
    { type: 'done', invalid_moves_removed: ['Qh5'] },
  ])
})

test('reassembles events split across network chunks and skips keepalives', async () => {
  const events = await collect(
    ': keepalive\n\n',
    'event: te',
    'xt\ndata: {"text": "hel',
    'lo"}\n\n: keepalive\n\nevent: error\ndata: {"message": "down"}\n\n',
  )

  expect(events).toEqual([
    { type: 'text', text: 'hello' },
    { type: 'error', message: 'down' },
  ])
})

test('ignores unknown events and malformed data', async () => {
  const events = await collect(
    'event: mystery\ndata: {"x": 1}\n\n',
    'event: text\ndata: not json\n\n',
    'event: text\ndata: {"text": 5}\n\n',
  )

  expect(events).toEqual([])
})
