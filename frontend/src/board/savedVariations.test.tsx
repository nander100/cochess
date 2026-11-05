import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from '../App'
import type { PipelineDeps } from '../analysis/pipeline'
import type { GameDetail } from '../api/types'
import { DETAIL, MOMENT, fakeDeps } from '../test/fakes'
import type { BoardMove } from './Board'
import { SAVE_DELAY_MS, SAVE_FAILED } from './useVariationSaver'

// SPEC_V3 §5.1 on the analysis board. chessground needs real layout, so the board is a stand-in
// that can play 2. Bc4 (after 1. e4 e5) or 2. d4.
vi.mock('./Board', () => ({
  Board: ({ onMove }: { onMove: (move: BoardMove) => void }) => (
    <div data-testid="board">
      <button type="button" onClick={() => onMove({ from: 'f1', to: 'c4' })}>
        play Bc4
      </button>
      <button type="button" onClick={() => onMove({ from: 'd2', to: 'd4' })}>
        play d4
      </button>
    </div>
  ),
}))

const BC4 = { start_path: ['e2e4', 'e7e5'], moves: ['f1c4'] }
const D4 = { start_path: ['e2e4', 'e7e5'], moves: ['d2d4'] }
const WAIT = { timeout: SAVE_DELAY_MS * 3 }

async function openGame(deps: PipelineDeps) {
  render(
    <MemoryRouter initialEntries={['/games/game-1']}>
      <App deps={deps} />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('button', { name: /^Moves/ }))
  return screen.findByLabelText('Moves')
}

const withVariations = (variations: GameDetail['variations'], extra: Partial<GameDetail> = {}) =>
  fakeDeps({ getGame: vi.fn(async () => ({ ...DETAIL, variations, ...extra })) })

test('a line played on the board is saved once the player pauses', async () => {
  const deps = fakeDeps()
  const moves = await openGame(deps)

  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))
  fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))
  expect(deps.api.saveVariations).not.toHaveBeenCalled()

  await waitFor(() => expect(deps.api.saveVariations).toHaveBeenCalledWith('game-1', [BC4]), WAIT)
})

test('playing a move of the game itself saves nothing', async () => {
  const deps = fakeDeps()
  const moves = await openGame(deps)
  fireEvent.click(within(moves).getByRole('button', { name: '1. e4' }))

  fireEvent.keyDown(window, { key: 'ArrowRight' })

  await new Promise((resolve) => setTimeout(resolve, SAVE_DELAY_MS * 1.5))
  expect(deps.api.saveVariations).not.toHaveBeenCalled()
})

test('saved variations come back, in their order', async () => {
  const moves = await openGame(withVariations([D4, BC4]))

  const lines = within(moves).getAllByRole('group', { name: 'Variation' })
  expect(lines.map((line) => line.textContent)).toEqual([expect.stringContaining('d4'), expect.stringContaining('Bc4')])
})

test("before the first save, a finished moment's tries and best move appear as variations", async () => {
  const revealed = {
    ...MOMENT, state: 'revealed' as const, best_san: 'd4', best_uci: 'd2d4',
    attempts: [{ uci: 'f1c4', san: 'Bc4', grade: 'mistake' as const }],
  } // prettier-ignore
  const before = await openGame(withVariations(null, { moments: [revealed] }))
  expect(within(before).getAllByRole('group', { name: 'Variation' })).toHaveLength(2)
})

test('a deleted moment line stays deleted once the list was saved', async () => {
  const revealed = { ...MOMENT, state: 'revealed' as const, best_san: 'd4', best_uci: 'd2d4' }
  const moves = await openGame(withVariations([], { moments: [revealed] }))

  expect(within(moves).queryByRole('group', { name: 'Variation' })).not.toBeInTheDocument()
})

test('deleting a variation from its menu removes it and saves', async () => {
  const deps = withVariations([BC4, D4])
  const moves = await openGame(deps)
  fireEvent.click(within(moves).getByRole('button', { name: '2. Bc4' }))
  const [first] = within(moves).getAllByRole('group', { name: 'Variation' })

  fireEvent.click(within(first).getByRole('button', { name: 'Variation options' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete variation' }))

  expect(within(moves).queryByRole('button', { name: '2. Bc4' })).not.toBeInTheDocument()
  expect(within(moves).getByRole('button', { name: '1... e5' })).toHaveAttribute('aria-current', 'step')
  await waitFor(() => expect(deps.api.saveVariations).toHaveBeenCalledWith('game-1', [D4]), WAIT)
})

test('right-click opens the menu; promoting moves the line first; Escape closes', async () => {
  const deps = withVariations([BC4, D4])
  const moves = await openGame(deps)
  const [first, second] = within(moves).getAllByRole('group', { name: 'Variation' })

  fireEvent.contextMenu(within(first).getByRole('button', { name: '2. Bc4' }))
  expect(screen.getByRole('menuitem', { name: 'Promote to main line of my notes' })).toBeDisabled()
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()

  fireEvent.contextMenu(within(second).getByRole('button', { name: '2. d4' }))
  fireEvent.click(screen.getByRole('menuitem', { name: 'Promote to main line of my notes' }))

  const lines = within(moves).getAllByRole('group', { name: 'Variation' })
  expect(lines[0]).toHaveTextContent('d4')
  await waitFor(() => expect(deps.api.saveVariations).toHaveBeenCalledWith('game-1', [D4, BC4]), WAIT)
})

test('a failed save says so', async () => {
  const deps = fakeDeps({ saveVariations: vi.fn(async () => { throw new Error('offline') }) })
  const moves = await openGame(deps)
  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))

  fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))

  expect(await screen.findByText(SAVE_FAILED, undefined, WAIT)).toBeInTheDocument()
})
