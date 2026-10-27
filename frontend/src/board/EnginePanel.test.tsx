import { act, fireEvent, render, screen } from '@testing-library/react'
import { useEffect, useState } from 'react'
import type { InfoLine } from '../engine/uci'
import { ENGINE_CONFIG, fakeEngine } from '../test/fakes'
import { EnginePanel, type LiveEngine } from './EnginePanel'
import { START_FEN } from './tree'

const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
// The real live tier's cap (backend config), so the stop message reads as it does in the app.
const CONFIG = { ...ENGINE_CONFIG, live: { ...ENGINE_CONFIG.live, hard_cap_ms: 10_000 } }
const MATED = 'rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3'

/** A live search the test drives: push lines, then finish it. */
interface Pending {
  fen: string
  signal: AbortSignal
  update: (lines: InfoLine[], depth: number) => void
  finish: () => void
}

function setup(initialFen = START_FEN) {
  const engine = fakeEngine()
  const searches: Pending[] = []
  vi.mocked(engine.analyzeLive).mockImplementation(
    (fen, _tier, update, signal) =>
      new Promise((resolve) => {
        const finish = () => resolve({ depth: 1, timeMs: 1, lines: [] })
        signal.addEventListener('abort', finish)
        searches.push({ fen, signal, update, finish })
      }),
  )
  const load = vi.fn(async (): Promise<LiveEngine> => ({ engine, config: CONFIG }))
  const onBest = vi.fn()
  let setFen: (fen: string) => void = () => {}
  function Harness() {
    const [fen, changeFen] = useState(initialFen)
    const [enabled, setEnabled] = useState(false)
    useEffect(() => {
      setFen = changeFen
    }, [])
    return <EnginePanel fen={fen} enabled={enabled} onToggle={setEnabled} load={load} onBest={onBest} />
  }
  render(<Harness />)
  return { engine, searches, load, onBest, setFen: (fen: string) => act(() => setFen(fen)) }
}

const toggle = () => fireEvent.click(screen.getByLabelText('Engine'))
const line = (multipv: number, cp: number, pv: string[]): InfoLine => ({
  depth: 12,
  multipv,
  score: { kind: 'cp', value: cp },
  pv,
})

test('off by default: nothing loads until the player turns it on', () => {
  const { load } = setup()

  expect(screen.getByLabelText('Engine')).not.toBeChecked()
  expect(load).not.toHaveBeenCalled()
})

test('turned on, it streams the top lines and reports the best one', async () => {
  const { searches, onBest } = setup()
  toggle()
  await vi.waitFor(() => expect(searches).toHaveLength(1))

  act(() => searches[0].update([line(1, 30, ['e2e4', 'e7e5']), line(2, 20, ['d2d4'])], 14))

  const lines = screen.getByRole('list', { name: 'Engine lines' })
  expect(lines).toHaveTextContent('+0.3 1. e4 e5')
  expect(lines).toHaveTextContent('+0.2 1. d4')
  expect(screen.getByRole('status')).toHaveTextContent('3 thread(s) · depth 14')
  expect(onBest).toHaveBeenLastCalledWith({ fen: START_FEN, line: expect.objectContaining({ evalText: '+0.3' }) })
})

test('a new position stops the old search and starts a new one', async () => {
  const { searches, setFen } = setup()
  toggle()
  await vi.waitFor(() => expect(searches).toHaveLength(1))

  setFen(AFTER_E4)

  expect(searches[0].signal.aborted).toBe(true)
  await vi.waitFor(() => expect(searches).toHaveLength(2))
  expect(searches[1].fen).toBe(AFTER_E4)
  expect(screen.queryByRole('list', { name: 'Engine lines' })).not.toBeInTheDocument()
})

test('says when it stopped at the time cap, and turning it off stops the search', async () => {
  const { searches } = setup()
  toggle()
  await vi.waitFor(() => expect(searches).toHaveLength(1))
  act(() => searches[0].update([line(1, 30, ['e2e4'])], 20))

  await act(async () => searches[0].finish())
  expect(screen.getByRole('status')).toHaveTextContent('depth 20 · stopped after 10 s')

  toggle()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('a finished game is not searched', () => {
  const { load } = setup(MATED)

  toggle()

  expect(screen.getByText('The game is over in this position.')).toBeInTheDocument()
  expect(load).not.toHaveBeenCalled()
})

test('an engine that fails to load says so', async () => {
  const { load } = setup()
  load.mockRejectedValue(new Error("The chess engine couldn't be loaded."))

  toggle()

  expect(await screen.findByRole('alert')).toHaveTextContent("couldn't be loaded")
})
