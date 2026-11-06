import { act, fireEvent, render, screen } from '@testing-library/react'
import type { LineLink, Playback } from '../api/types'
import { fakeApi } from '../test/fakes'
import { PlaybackBar } from './PlaybackBar'
import { usePlayback } from './usePlayback'

// 1. e4 e5 2. Nf3 Nc6: four moves; the backend says to stop after two.
const LINK: LineLink = {
  index: 0, char_offset: 0, line_id: 'line-1', ref: 'here.engine1', label: 'the main line', kind: 'engine',
  start_path_uci: [], moves_uci: ['e2e4', 'e7e5', 'g1f3', 'b8c6'],
} // prettier-ignore

function settled(ply: number): Playback {
  return {
    line_id: 'line-1', start_fen: '', moves_uci: LINK.moves_uci, moves_san: [], evals: ['0.0', '+0.3', '+0.2', '+0.3', '+0.2'],
    win_pcts: [50, 53, 52, 53, 52], settle_ply: ply, caption: 'White is slightly better.',
  } // prettier-ignore
}

function Harness({ playback: answer }: { playback: () => Promise<Playback> }) {
  const player = usePlayback({ api: fakeApi({ playback: vi.fn(answer) }), scan: vi.fn(async (fen: string) => ({ ply: null, fen, tier: 'scan' as const, depth: 12, time_ms: 1, lines: [] })) }, 1)
  return (
    <>
      <button type="button" onClick={() => player.play(LINK)}>
        play
      </button>
      <div data-testid="board">{player.view?.lastMove ?? "start"}</div>
      {player.state && <PlaybackBar playback={player} state={player.state} onWalk={vi.fn()} onSave={vi.fn()} saved={false} />}
    </>
  )
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

async function tick(times = 1) {
  for (let i = 0; i < times; i++) await act(async () => vi.advanceTimersByTime(1000))
}

test('the line plays one move a second and stops at the settle point with the caption', async () => {
  render(<Harness playback={async () => settled(2)} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'play' })))
  expect(screen.getByTestId('board')).toHaveTextContent('start')

  await tick()
  expect(screen.getByTestId('board')).toHaveTextContent('e2e4')
  await tick(3)

  expect(screen.getByTestId('board')).toHaveTextContent('e7e5') // stopped after two moves
  expect(screen.getByRole('status')).toHaveTextContent('White is slightly better.')
  expect(screen.getByText('Move 2 of 4')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Continue the line' }))
  await tick(3)
  expect(screen.getByTestId('board')).toHaveTextContent('b8c6')
  expect(screen.queryByRole('button', { name: 'Continue the line' })).not.toBeInTheDocument()
})

test('without a settle point the whole line plays; the step buttons pause', async () => {
  render(<Harness playback={() => new Promise<Playback>(() => {})} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'play' })))

  await tick(2)
  fireEvent.click(screen.getByRole('button', { name: 'Step back' }))
  expect(screen.getByTestId('board')).toHaveTextContent('e2e4')
  await tick(3)
  expect(screen.getByTestId('board')).toHaveTextContent('e2e4') // paused
  fireEvent.click(screen.getByRole('button', { name: 'Play' }))
  await tick(5)
  expect(screen.getByText('Move 4 of 4')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('end of the line')
})

test('a settle point that arrives late stops playback where it is', async () => {
  let arrive: (p: Playback) => void = () => {}
  render(<Harness playback={() => new Promise<Playback>((resolve) => { arrive = resolve })} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'play' })))
  await tick(3)

  await act(async () => arrive(settled(2)))

  expect(screen.getByText('Move 3 of 4')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('White is slightly better.')
})

test('back to position closes playback', async () => {
  render(<Harness playback={async () => settled(2)} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'play' })))

  fireEvent.click(screen.getByRole('button', { name: 'Back to position' }))

  expect(screen.queryByRole('region', { name: 'Line playback' })).not.toBeInTheDocument()
})
