import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from './App'
import type { PipelineDeps } from './analysis/pipeline'
import { ApiError } from './api/client'
import type { CoachEvent } from './api/sse'
import type { BoardMove } from './board/Board'
import { DETAIL, PROFILE, fakeDeps } from './test/fakes'

// chessground needs real layout; the analysis board is tested with a stand-in that shows the
// position and can play a move.
vi.mock('./board/Board', () => ({
  Board: ({ fen, onMove }: { fen: string; onMove: (move: BoardMove) => void }) => (
    <div data-testid="board" data-fen={fen}>
      <button type="button" onClick={() => onMove({ from: 'f1', to: 'c4' })}>
        play Bc4
      </button>
    </div>
  ),
}))

function renderApp(deps: PipelineDeps, path = '/new') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App deps={deps} />
    </MemoryRouter>,
  )
}

async function submitGame() {
  fireEvent.change(await screen.findByLabelText(/your game/i), {
    target: { value: '1. e4 e5 2. Nf3 *' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
}

const LOGGED_OUT = new ApiError(401, "You're not logged in. Ask the owner for a new login link.")

test('renders the app title', async () => {
  renderApp(fakeDeps())

  expect(await screen.findByRole('heading', { name: 'CoChess' })).toBeInTheDocument()
})

test('a new game is analyzed, then opens on the board with engine details and a synopsis', async () => {
  const deps = fakeDeps()
  renderApp(deps)

  await submitGame()

  expect(await screen.findByRole('heading', { name: /Alex – Rival/ })).toBeInTheDocument()
  expect(deps.api.getGame).toHaveBeenCalledWith('game-1')
  expect(screen.getByText(/stockfish-19-lite, 3 thread\(s\)/)).toBeInTheDocument()
  expect(await screen.findByText('A tidy game.')).toBeInTheDocument()
  expect(deps.api.streamSynopsis).toHaveBeenCalledOnce()
})

test('shows the server error when the PGN is rejected', async () => {
  const deps = fakeDeps({
    createGame: vi.fn(async () => {
      throw new ApiError(422, "Non-standard starting positions aren't supported.")
    }),
  })
  renderApp(deps)

  await submitGame()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Non-standard starting positions aren't supported.",
  )
  expect(screen.getByRole('button', { name: 'Analyze' })).toBeEnabled()
})

test('a coach error is shown in the synopsis panel and can be retried', async () => {
  const streamSynopsis = vi
    .fn()
    .mockImplementationOnce(async (_g: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'error', message: 'The coach is unavailable right now.' })
    })
    .mockImplementationOnce(async (_g: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'text', text: '### Overall\nSecond time lucky.' })
      emit({ type: 'done', invalid_moves_removed: [] })
    })
  renderApp(fakeDeps({ streamSynopsis }))
  await submitGame()

  expect(await screen.findByText('The coach is unavailable right now.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

  expect(await screen.findByText('Second time lucky.')).toBeInTheDocument()
})

test('my games lists the games; opening one does not write a synopsis by itself', async () => {
  const deps = fakeDeps({
    listGames: vi.fn(async () => [
      {
        id: 'game-1',
        played_at: '2026-10-01T18:04:05Z',
        opponent: 'Rival',
        user_color: 'white' as const,
        user_result: 'win' as const,
        time_control: '600+5',
        opening: 'Ruy Lopez',
        accuracy: 81.2,
        status: 'analyzed' as const,
      },
    ]),
  })
  renderApp(deps, '/')

  const table = await screen.findByRole('table')
  expect(within(table).getByText('Rival')).toBeInTheDocument()
  expect(within(table).getByText('81.2%')).toBeInTheDocument()
  fireEvent.click(within(table).getByRole('link'))

  fireEvent.click(await screen.findByRole('button', { name: 'Write a synopsis of this game' }))
  expect(await screen.findByText('A tidy game.')).toBeInTheDocument()
  expect(deps.api.streamSynopsis).toHaveBeenCalledOnce()
})

test('a reopened game shows its stored synopsis and chat', async () => {
  const deps = fakeDeps({
    getGame: vi.fn(async () => ({
      ...DETAIL,
      synopsis: { text: '### Overall\nStored synopsis.', invalid_moves_removed: [] },
      chat: [
        { role: 'player' as const, text: 'Why was Nf3 a mistake?' },
        { role: 'coach' as const, text: 'It allowed a pin.' },
      ],
    })),
  })
  renderApp(deps, '/games/game-1')

  expect(await screen.findByText('Stored synopsis.')).toBeInTheDocument()
  expect(screen.getByText('Why was Nf3 a mistake?')).toBeInTheDocument()
  expect(screen.getByText('It allowed a pin.')).toBeInTheDocument()
  expect(deps.api.streamSynopsis).not.toHaveBeenCalled()
})

test('the move list marks my mistake, and moves are explored with clicks, the board and arrow keys', async () => {
  renderApp(fakeDeps(), '/games/game-1')

  const moves = await screen.findByLabelText('Moves')
  expect(within(moves).getByRole('button', { name: '2. Nf3, mistake' })).toHaveTextContent('Nf3?')

  fireEvent.click(within(moves).getByRole('button', { name: '1... e5' }))
  expect(screen.getByTestId('board').dataset.fen).toBe(DETAIL.moves[2].fen_before)

  fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))
  const variation = await within(moves).findByRole('group', { name: 'Variation' })
  expect(within(variation).getByRole('button', { name: '2. Bc4' })).toHaveAttribute('aria-current', 'step')

  fireEvent.keyDown(window, { key: 'ArrowLeft' })
  expect(within(moves).getByRole('button', { name: '1... e5' })).toHaveAttribute('aria-current', 'step')
  fireEvent.keyDown(window, { key: 'ArrowRight' }) // forward follows the game, not the variation
  expect(within(moves).getByRole('button', { name: '2. Nf3, mistake' })).toHaveAttribute('aria-current', 'step')
})

test('the eval bar follows the position', async () => {
  renderApp(fakeDeps(), '/games/game-1')

  const bar = await screen.findByRole('meter', { name: 'Evaluation' })
  expect(bar).toHaveAttribute('aria-valuenow', '50')
  fireEvent.click(screen.getByRole('button', { name: '2. Nf3, mistake' }))

  expect(bar).toHaveAttribute('aria-valuenow', '30')
  expect(bar).toHaveAttribute('aria-valuetext', '-1.0')
})

test('an unfinished analysis resumes with the verify step only', async () => {
  const unfinished = { ...DETAIL, status: 'scanned' as const, verify_fens: [DETAIL.moves[2].fen_before] }
  const deps = fakeDeps({
    getGame: vi.fn().mockResolvedValueOnce(unfinished).mockResolvedValue(DETAIL),
  })
  renderApp(deps, '/games/game-1')

  fireEvent.click(await screen.findByRole('button', { name: 'Resume analysis' }))

  expect(await screen.findByRole('button', { name: 'Write a synopsis of this game' })).toBeInTheDocument()
  expect(deps.api.submitScan).not.toHaveBeenCalled()
  expect(deps.api.submitVerify).toHaveBeenCalledWith('game-1', [
    expect.objectContaining({ fen: DETAIL.moves[2].fen_before, tier: 'verify' }),
  ])
})

test("a game that isn't yours or doesn't exist says so", async () => {
  renderApp(fakeDeps({ getGame: vi.fn().mockRejectedValue(new ApiError(404, 'Game not found.')) }), '/games/x')

  expect(await screen.findByRole('alert')).toHaveTextContent("doesn't exist, or it isn't yours")
})

test('a what-if question in the chat runs the deep tier on the engine', async () => {
  const deps = fakeDeps({
    sendChat: vi.fn(async (_g: string, _m: string, emit: (event: CoachEvent) => void) => {
      emit({ type: 'engine_request', request_id: 'r1', positions: [{ fen: 'fen-1 b', label: 'position' }] })
    }),
    submitEngineResult: vi.fn(async (_g: string, _r: string, _res: unknown, emit: (event: CoachEvent) => void) => {
      emit({ type: 'text', text: 'The engine likes your idea.' })
      emit({ type: 'done', invalid_moves_removed: [] })
    }),
  })
  renderApp(deps, '/games/game-1')

  fireEvent.change(await screen.findByLabelText('Your question'), { target: { value: 'What if e5?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByText('The engine likes your idea.')).toBeInTheDocument()
  expect(deps.engine.analyze).toHaveBeenLastCalledWith(
    { fen: 'fen-1 b', ply: null },
    'deep',
    expect.objectContaining({ multipv: 4 }),
  )
})

test('without a session the app asks for a login link', async () => {
  renderApp(fakeDeps({ me: vi.fn().mockRejectedValue(LOGGED_OUT) }))

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
  expect(screen.queryByLabelText(/your game/i)).not.toBeInTheDocument()
})

test('a 401 in the middle of a session shows the logged-out message', async () => {
  renderApp(fakeDeps({ createGame: vi.fn().mockRejectedValue(LOGGED_OUT) }))

  await submitGame()

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
})

test('the header shows who is logged in, and logging out ends the session', async () => {
  const deps = fakeDeps()
  renderApp(deps)

  expect(await screen.findByText('Alex')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Log out' }))

  expect(await screen.findByRole('alert')).toHaveTextContent("You're not logged in")
  expect(deps.api.logout).toHaveBeenCalled()
})

test('a login link redeems the token, then opens my games', async () => {
  const deps = fakeDeps()
  renderApp(deps, '/redeem#token=abc123')

  expect(await screen.findByText(/No games yet/)).toBeInTheDocument()
  expect(deps.api.redeem).toHaveBeenCalledTimes(1)
  expect(deps.api.redeem).toHaveBeenCalledWith('abc123')
})

test('a used login link shows why it failed', async () => {
  const used = new ApiError(400, 'This login link has expired or was already used.')
  renderApp(fakeDeps({ redeem: vi.fn().mockRejectedValue(used) }), '/redeem#token=abc123')

  expect(await screen.findByRole('alert')).toHaveTextContent('expired or was already used')
})

test('a new player fills in the profile first, then sees their games', async () => {
  const blank = { ...PROFILE, elo: null, time_control: null, complete: false }
  const deps = fakeDeps({ me: vi.fn(async () => blank) })
  renderApp(deps, '/')

  fireEvent.change(await screen.findByLabelText(/rating/i), { target: { value: '1450' } })
  fireEvent.change(screen.getByLabelText(/time control/i), { target: { value: 'blitz' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

  expect(await screen.findByText(/No games yet/)).toBeInTheDocument()
  expect(deps.api.updateMe).toHaveBeenCalledWith({
    name: 'Alex',
    elo: 1450,
    time_control: 'blitz',
    playstyle: '',
  })
})
