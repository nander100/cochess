import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from '../App'
import type { PipelineDeps } from '../analysis/pipeline'
import type { CoachEvent } from '../api/sse'
import type { Annotation, ChatEntry } from '../api/types'
import { DETAIL, fakeDeps } from '../test/fakes'

// SPEC_V3 §6.3 on the analysis board. chessground needs real layout, so the board is a stand-in
// that lists the coach shapes it was given.
vi.mock('./Board', () => ({
  Board: ({ annotations = [] }: { annotations?: readonly Annotation[] }) => (
    <output data-testid="coach-shapes">
      {annotations
        .flatMap((a) => [...a.arrows.map((x) => `${x.orig}${x.dest}:${x.color}`), ...a.squares.map((x) => `${x.square}:${x.color}`)])
        .join(' ')}
    </output>
  ),
}))

const AFTER_E5 = ['e2e4', 'e7e5'] // stored engine lines exist here (DETAIL), so chat can run
const THREAT: Annotation = { tag_index: 0, char_offset: 4, arrows: [{ orig: 'd1', dest: 'h5', color: 'blue' }], squares: [] }
const SQUARE: Annotation = { tag_index: 1, char_offset: 30, arrows: [], squares: [{ square: 'f7', color: 'red' }] }

const CHAT: ChatEntry[] = [
  { role: 'player', text: 'What now?', where: 'after 1... e5', path_uci: AFTER_E5, annotations: [] },
  {
    role: 'coach',
    text: 'See [board](cc:board/0) the queen idea, and [board](cc:board/1) the weak pawn.',
    where: null,
    path_uci: AFTER_E5,
    annotations: [THREAT, SQUARE],
  },
]

function shapes() {
  return screen.getByTestId('coach-shapes').textContent
}

async function openGame(deps: PipelineDeps) {
  render(
    <MemoryRouter initialEntries={['/games/game-1']}>
      <App deps={deps} />
    </MemoryRouter>,
  )
  await screen.findByTestId('coach-shapes')
  fireEvent.click(await screen.findByRole('button', { name: /^Moves/ }))
  return screen.getByLabelText('Moves')
}

const withChat = (chat: ChatEntry[]) => fakeDeps({ getGame: vi.fn(async () => ({ ...DETAIL, chat })) })

test("a stored message's shapes are drawn on its position only, and come back on return", async () => {
  const moves = await openGame(withChat(CHAT))
  expect(shapes()).toBe('') // the board opens at the start

  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))
  expect(shapes()).toBe('d1h5:blue f7:red')

  fireEvent.click(within(moves).getByRole('button', { name: /^2\. Nf3/ }))
  expect(shapes()).toBe('')

  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))
  expect(shapes()).toBe('d1h5:blue f7:red')
})

test('hovering a tag shows only that tag; leaving it shows the whole message again', async () => {
  const moves = await openGame(withChat(CHAT))
  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))
  const [, second] = screen.getAllByRole('button', { name: 'Show this on the board' })

  fireEvent.mouseEnter(second)
  expect(shapes()).toBe('f7:red')

  fireEvent.mouseLeave(second)
  expect(shapes()).toBe('d1h5:blue f7:red')
})

test("clicking a tag while the board is elsewhere goes to the message's position", async () => {
  await openGame(withChat(CHAT))
  const [first] = screen.getAllByRole('button', { name: 'Show this on the board' })

  fireEvent.click(first)

  expect(shapes()).toBe('d1h5:blue')
  expect(screen.getByText(/Your questions are about the board: after 1\.\.\. e5/)).toBeInTheDocument()
})

test("a new answer's shapes are drawn as it arrives", async () => {
  const deps = fakeDeps({
    sendChat: vi.fn(async (_id: string, _body: unknown, emit: (e: CoachEvent) => void) => {
      emit({ type: 'text', text: 'Mind [board](cc:board/0).' })
      emit({ type: 'annotation', annotation: { ...SQUARE, tag_index: 0 } })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  const moves = await openGame(deps)
  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))

  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Any danger?' } })
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))

  expect(await screen.findByRole('button', { name: 'Show this on the board' })).toBeInTheDocument()
  expect(shapes()).toBe('f7:red')
  expect(deps.api.sendChat).toHaveBeenCalledWith('game-1', expect.objectContaining({ path_uci: AFTER_E5 }), expect.any(Function))
})
