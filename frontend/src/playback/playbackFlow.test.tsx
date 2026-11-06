import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from '../App'
import type { CoachEvent } from '../api/sse'
import type { LineLink } from '../api/types'
import { fakeDeps } from '../test/fakes'

// SPEC_V3 §9.5 on the analysis board, with a stand-in board that reports what it shows.
vi.mock('../board/Board', () => ({
  Board: (props: { fen: string; lastMove: string | null; movable: boolean }) => (
    <div data-testid="board" data-fen={props.fen} data-last={props.lastMove ?? ''} data-movable={String(props.movable)} />
  ),
}))

const LINK: LineLink = {
  index: 0, char_offset: 30, line_id: 'line-1', ref: 'here.engine1', label: 'watch the idea', kind: 'engine',
  start_path_uci: ['e2e4', 'e7e5'], moves_uci: ['g1f3', 'b8c6', 'f1b5'],
} // prettier-ignore

test('a line link in a coach answer plays on the board; Esc goes back to the position', async () => {
  const deps = fakeDeps({
    sendChat: vi.fn(async (_id: string, _body: unknown, emit: (e: CoachEvent) => void) => {
      emit({ type: 'text', text: 'There is a plan here: [watch the idea](cc:line/0).' })
      emit({ type: 'line_link', link: LINK })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  render(
    <MemoryRouter initialEntries={['/games/game-1']}>
      <App deps={deps} />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('button', { name: /^Moves/ }))
  fireEvent.click(within(screen.getByLabelText('Moves')).getByRole('button', { name: '1... e5' }))
  const before = screen.getByTestId('board').getAttribute('data-fen')
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Any plan?' } })
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))

  fireEvent.click(await screen.findByRole('button', { name: 'watch the idea' }))

  expect(screen.getByRole('region', { name: 'Line playback' })).toBeInTheDocument()
  expect(screen.getByTestId('board')).toHaveAttribute('data-movable', 'false')
  expect(screen.getByText('Move 0 of 3')).toBeInTheDocument()
  expect(deps.api.playback).toHaveBeenCalledWith('line-1', expect.any(Array)) // scanned, then settled

  fireEvent.keyDown(window, { key: 'ArrowRight' })
  expect(screen.getByTestId('board')).toHaveAttribute('data-last', 'g1f3')

  fireEvent.keyDown(window, { key: 'Escape' })
  expect(screen.queryByRole('region', { name: 'Line playback' })).not.toBeInTheDocument()
  expect(screen.getByTestId('board')).toHaveAttribute('data-fen', before)
})
