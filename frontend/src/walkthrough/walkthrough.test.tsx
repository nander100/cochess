import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from '../App'
import type { PipelineDeps } from '../analysis/pipeline'
import type { CoachEvent } from '../api/sse'
import type { Annotation, WalkthroughRequest } from '../api/types'
import { SAVE_DELAY_MS } from '../board/useVariationSaver'
import { DETAIL, MOMENT, fakeDeps, walkthroughFor } from '../test/fakes'

// SPEC_V3 §7.3 on the analysis board, with a stand-in board that reports what it shows.
vi.mock('../board/Board', () => ({
  Board: (props: { fen: string; lastMove: string | null; movable: boolean; annotations?: readonly Annotation[] }) => (
    <output data-testid="board" data-fen={props.fen} data-last={props.lastMove ?? ''} data-movable={String(props.movable)}>
      {(props.annotations ?? []).flatMap((a) => a.arrows.map((x) => `${x.orig}${x.dest}:${x.color}`)).join(' ')}
    </output>
  ),
}))

const AFTER_E5 = DETAIL.moves[2].fen_before // the stored line here is changed to 2. Bc4 Nf6
const LINE = ['f1c4', 'g8f6']
const STORED = [{ ...DETAIL.engine_results[0], lines: [{ ...DETAIL.engine_results[0].lines[0], moves_uci: LINE }] }]
const ARROW: Annotation = { tag_index: 0, char_offset: 0, arrows: [{ orig: 'c4', dest: 'f7', color: 'red' }], squares: [] }

function board() {
  return screen.getByTestId('board')
}

async function openGame(deps: PipelineDeps) {
  render(
    <MemoryRouter initialEntries={['/games/game-1']}>
      <App deps={deps} />
    </MemoryRouter>,
  )
  await screen.findByTestId('board')
  fireEvent.click(await screen.findByRole('button', { name: /^Moves/ }))
  fireEvent.click(within(screen.getByLabelText('Moves')).getByRole('button', { name: '1... e5' }))
}

function withWalk(walkthrough = vi.fn(async (_id: string, body: WalkthroughRequest, emit: (e: CoachEvent) => void) => {
  const walk = walkthroughFor(body)
  walk.steps[0] = { ...walk.steps[0], annotation: ARROW }
  emit({ type: 'walkthrough', walkthrough: walk })
  emit({ type: 'done', invalid_moves_removed: [] })
})) {
  return fakeDeps({ getGame: vi.fn(async () => ({ ...DETAIL, engine_results: STORED })), walkthrough })
}

test("the engine's line is walked through step by step on the board, then back to the game", async () => {
  const deps = withWalk()
  await openGame(deps)

  fireEvent.click(screen.getByRole('button', { name: "Walk me through the engine's line" }))

  const panel = await screen.findByRole('region', { name: 'Walkthrough' })
  expect(within(panel).getByText('Here is the idea of this line.')).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Chat with your coach' })).not.toBeInTheDocument()
  expect(board()).toHaveAttribute('data-fen', AFTER_E5)
  expect(board()).toHaveAttribute('data-movable', 'false')
  expect(deps.api.walkthrough).toHaveBeenCalledWith(
    'game-1', { start_path_uci: ['e2e4', 'e7e5'], line_uci: LINE, step_results: [] }, expect.any(Function),
  ) // prettier-ignore

  fireEvent.click(within(panel).getByRole('button', { name: 'Start ▶' }))
  expect(within(panel).getByText('Step 1 of 2: 2. Bc4')).toBeInTheDocument()
  expect(board()).toHaveAttribute('data-last', 'f1c4')
  expect(board()).toHaveTextContent('c4f7:red')

  fireEvent.keyDown(window, { key: 'ArrowRight' })
  expect(within(panel).getByText(/Step 2 of 2/)).toBeInTheDocument()
  expect(within(panel).getByText('Remember the plan.')).toBeInTheDocument()
  expect(board().textContent).toBe('') // step 2 has no shapes

  fireEvent.keyDown(window, { key: 'Escape' })
  expect(screen.queryByRole('region', { name: 'Walkthrough' })).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Chat with your coach' })).toBeInTheDocument()
  expect(board()).toHaveAttribute('data-fen', AFTER_E5)
  expect(board()).toHaveAttribute('data-movable', 'true')
})

test('W walks the top line; saving adds it to the saved variations', async () => {
  const deps = withWalk()
  await openGame(deps)

  fireEvent.keyDown(window, { key: 'w' })
  const panel = await screen.findByRole('region', { name: 'Walkthrough' })
  await act(async () => fireEvent.click(within(panel).getByRole('button', { name: 'Save as variation' })))

  expect(within(panel).getByRole('button', { name: 'Saved as a variation' })).toBeDisabled()
  await waitFor(
    () => expect(deps.api.saveVariations).toHaveBeenCalledWith('game-1', [{ start_path: ['e2e4', 'e7e5'], moves: LINE }]),
    { timeout: SAVE_DELAY_MS * 3 },
  )
})

test('a failed walkthrough shows the reason and can be tried again', async () => {
  let attempts = 0
  const deps = withWalk(vi.fn(async (_id: string, body: WalkthroughRequest, emit: (e: CoachEvent) => void) => {
    attempts += 1
    if (attempts === 1) {
      emit({ type: 'error', message: "The coach couldn't put this walkthrough together. Please try again." })
      return
    }
    emit({ type: 'walkthrough', walkthrough: walkthroughFor(body) })
  }))
  await openGame(deps)

  fireEvent.click(screen.getByRole('button', { name: "Walk me through the engine's line" }))
  expect(await screen.findByRole('alert')).toHaveTextContent("couldn't put this walkthrough together")
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('Here is the idea of this line.')).toBeInTheDocument()
})

test('a saved variation can be walked through from its menu', async () => {
  const deps = fakeDeps({
    getGame: vi.fn(async () => ({ ...DETAIL, variations: [{ start_path: ['e2e4', 'e7e5'], moves: ['d2d4', 'e5d4'] }] })),
  })
  await openGame(deps)

  fireEvent.click(screen.getByRole('button', { name: 'Variation options' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Walk me through it' }))

  await screen.findByRole('region', { name: 'Walkthrough' })
  expect(deps.api.walkthrough).toHaveBeenCalledWith(
    'game-1', { start_path_uci: ['e2e4', 'e7e5'], line_uci: ['d2d4', 'e5d4'], step_results: [] }, expect.any(Function),
  ) // prettier-ignore
})

test('the chat, with what was said before, is still there after a walkthrough', async () => {
  const deps = withWalk()
  await openGame(deps)
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Is Bc4 good?' } })
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
  expect(await screen.findByText('Good question.')).toBeInTheDocument()

  fireEvent.keyDown(window, { key: 'w' })
  await screen.findByRole('region', { name: 'Walkthrough' })
  fireEvent.click(screen.getByRole('button', { name: 'Back to game' }))

  expect(screen.getByText('Good question.')).toBeVisible()
  expect(screen.getByText('Is Bc4 good?')).toBeVisible()
  expect(screen.getByLabelText('Moves')).toBeInTheDocument() // the moves panel stayed open
})

test("once a moment is revealed, its position offers the engine's best line to walk through", async () => {
  const intro = { role: 'coach' as const, text: 'What would you play instead?', kind: 'intro' }
  const started = { ...DETAIL, engine_results: [], moments: [{ ...MOMENT, state: 'attempt' as const, messages: [intro] }] }
  const revealed = {
    ...DETAIL,
    engine_results: STORED, // the moment's position: its lines are no longer withheld
    moments: [{ ...MOMENT, state: 'revealed' as const, messages: [intro], best_san: 'Bc4', best_uci: 'f1c4' }],
  }
  const deps = fakeDeps({ getGame: vi.fn().mockResolvedValueOnce(started).mockResolvedValue(revealed) })
  render(
    <MemoryRouter initialEntries={['/games/game-1']}>
      <App deps={deps} />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('tab', { name: /Critical moments/ }))
  expect(screen.queryByRole('button', { name: "Walk me through the engine's line" })).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Show the answer' }))

  fireEvent.click(await screen.findByRole('button', { name: "Walk me through the engine's line" }))
  await screen.findByRole('region', { name: 'Walkthrough' })
  expect(deps.api.walkthrough).toHaveBeenCalledWith(
    'game-1', { start_path_uci: ['e2e4', 'e7e5'], line_uci: LINE, step_results: [] }, expect.any(Function),
  ) // prettier-ignore
})
