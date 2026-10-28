import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from './App'
import type { PipelineDeps } from './analysis/pipeline'
import { ApiError } from './api/client'
import type { CoachEvent } from './api/sse'
import type { BoardMove } from './board/Board'
import type { GameDetail, MomentInfo } from './api/types'
import { DETAIL, MOMENT, PROFILE, fakeDeps } from './test/fakes'

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
        { role: 'player' as const, text: 'Why was Nf3 a mistake?', where: 'after 2. Nf3' },
        { role: 'coach' as const, text: 'It allowed a pin.', where: null },
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
    sendChat: vi.fn(async (_g: string, _m: unknown, emit: (event: CoachEvent) => void) => {
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
  const deps = fakeDeps({ redeem: vi.fn().mockRejectedValue(used), me: vi.fn().mockRejectedValue(LOGGED_OUT) })
  renderApp(deps, '/redeem#token=abc123')

  expect(await screen.findByRole('alert')).toHaveTextContent('expired or was already used')
})

test('reopening a used login link while logged in just opens my games', async () => {
  const used = new ApiError(400, 'This login link has expired or was already used.')
  renderApp(fakeDeps({ redeem: vi.fn().mockRejectedValue(used) }), '/redeem#token=abc123')

  expect(await screen.findByText(/No games yet/)).toBeInTheDocument()
  expect(screen.queryByText(/expired or was already used/)).not.toBeInTheDocument()
})

test('a new player fills in the profile first, then sees the assessment (which they can skip)', async () => {
  const blank = { ...PROFILE, elo: null, time_control: null, complete: false }
  const deps = fakeDeps({ me: vi.fn(async () => blank) })
  renderApp(deps, '/')

  fireEvent.change(await screen.findByLabelText(/rating/i), { target: { value: '1450' } })
  fireEvent.change(screen.getByLabelText(/time control/i), { target: { value: 'blitz' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save and continue' }))

  expect(await screen.findByRole('heading', { name: 'Your baseline assessment' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('link', { name: 'Skip for now' }))
  expect(await screen.findByText(/No games yet/)).toBeInTheDocument()
  expect(deps.api.updateMe).toHaveBeenCalledWith({
    name: 'Alex',
    elo: 1450,
    time_control: 'blitz',
    playstyle: '',
  })
})

describe('chat and Explain are about the position on the board', () => {
  async function askHere(deps: ReturnType<typeof fakeDeps>, message: string) {
    fireEvent.change(await screen.findByLabelText('Your question'), { target: { value: message } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText('Good question.')
    return vi.mocked(deps.api.sendChat).mock.calls.at(-1)![1]
  }

  test('a game position the backend has lines for: just the path', async () => {
    const deps = fakeDeps()
    renderApp(deps, '/games/game-1')
    // DETAIL stores a verify result for the position after 1... e5.
    fireEvent.click(await screen.findByRole('button', { name: '1... e5' }))

    const body = await askHere(deps, 'What now?')

    expect(body).toEqual({ message: 'What now?', path_uci: ['e2e4', 'e7e5'] })
    expect(deps.engine.analyze).not.toHaveBeenCalled()
    expect(screen.getByText('You').parentElement).toHaveTextContent('after 1... e5')
  })

  test('a variation: the browser analyzes it first and sends its result', async () => {
    const deps = fakeDeps()
    renderApp(deps, '/games/game-1')
    fireEvent.click(await screen.findByRole('button', { name: '1... e5' }))
    fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))

    const body = await askHere(deps, 'Is Bc4 better?')

    expect(deps.engine.analyze).toHaveBeenCalledWith(
      { fen: expect.stringContaining('2B1P3'), ply: null },
      'verify',
      expect.objectContaining({ multipv: 4 }),
    )
    expect(body).toMatchObject({
      message: 'Is Bc4 better?',
      path_uci: ['e2e4', 'e7e5', 'f1c4'],
      engine_result: expect.objectContaining({ tier: 'verify' }),
    })
    expect(screen.getByText('You').parentElement).toHaveTextContent('after 2. Bc4, in your line')
  })

  test('Explain sends the board position and the answer appears in the chat', async () => {
    const deps = fakeDeps()
    renderApp(deps, '/games/game-1')
    fireEvent.click(await screen.findByRole('button', { name: '1... e5' }))

    fireEvent.click(screen.getByRole('button', { name: 'Explain this position' }))

    expect(await screen.findByText('Here is the position.')).toBeInTheDocument()
    expect(deps.api.explain).toHaveBeenCalledWith('game-1', { path_uci: ['e2e4', 'e7e5'] }, expect.any(Function))
  })
})

describe('critical moments', () => {
  // The fake game's moment is White's 2. Nf3; the position before it is after 1. e4 e5.
  const BEFORE_NF3 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
  const withMoment = (moment: Partial<MomentInfo> = {}, extra: Partial<GameDetail> = {}): GameDetail => ({
    ...DETAIL,
    moments: [{ ...MOMENT, ...moment }],
    ...extra,
  })
  const INTRO = { role: 'coach' as const, text: 'What would you play instead, and why?', kind: 'intro' }

  async function openMoments() {
    fireEvent.click(await screen.findByRole('tab', { name: /Critical moments \(0\/1\)/ }))
  }

  test('the synopsis is collapsed as a spoiler while a moment is unsolved', async () => {
    const synopsis = { text: 'You should have played 2. d4.', invalid_moves_removed: [] }
    const deps = fakeDeps({ getGame: vi.fn(async () => withMoment({}, { synopsis })) })
    renderApp(deps, '/games/game-1')

    const summary = await screen.findByText(/Show the synopsis \(spoilers/)

    expect(summary.closest('details')).not.toHaveAttribute('open')
  })

  test('a moment locks the board to its position, and a move there is only a candidate', async () => {
    const started = withMoment({ state: 'intro', messages: [INTRO] })
    const deps = fakeDeps({ getGame: vi.fn().mockResolvedValueOnce(withMoment()).mockResolvedValue(started) })
    renderApp(deps, '/games/game-1')
    await openMoments()

    expect(screen.getByTestId('board')).toHaveAttribute('data-fen', BEFORE_NF3)
    expect(screen.queryByRole('region', { name: 'Live engine' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous move (←)' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Start this moment' }))
    expect(await screen.findByText('What would you play instead, and why?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))

    expect(screen.getByText('Your move:').parentElement).toHaveTextContent('2. Bc4')
    expect(screen.getByTestId('board').getAttribute('data-fen')).toContain('2B1P3')
    expect(screen.queryByRole('button', { name: '2. Bc4' })).not.toBeInTheDocument() // not in the tree
  })

  test('checking a move sends the engine searches before and after it', async () => {
    const started = withMoment({ state: 'intro', messages: [INTRO] })
    const deps = fakeDeps({ getGame: vi.fn().mockResolvedValueOnce(started).mockResolvedValue(started) })
    renderApp(deps, '/games/game-1')
    fireEvent.click(await screen.findByRole('tab', { name: /Critical moments/ }))
    fireEvent.click(screen.getByRole('button', { name: 'play Bc4' }))
    fireEvent.change(screen.getByLabelText('Why this move? (optional)'), { target: { value: 'Aim at f7' } })

    fireEvent.click(screen.getByRole('button', { name: 'Check my move' }))

    expect(await screen.findByText('Mistake')).toBeInTheDocument()
    const fens = vi.mocked(deps.engine.analyze).mock.calls.map(([item, tier]) => [item.fen, tier])
    expect(fens).toEqual([
      [BEFORE_NF3, 'deep'],
      [expect.stringContaining('2B1P3'), 'deep'],
    ])
    const [, index, body] = vi.mocked(deps.api.momentAttempt).mock.calls[0]
    expect(index).toBe(1)
    expect(body).toMatchObject({ move_uci: 'f1c4', reasoning: 'Aim at f7' })
    expect(screen.getByText('Play your move on the board.')).toBeInTheDocument() // the candidate is cleared
  })

  test('after a reveal the tries and the best move are variations, and the board unlocks', async () => {
    const started = withMoment({ state: 'attempt', messages: [INTRO], attempts: [{ uci: 'f1c4', san: 'Bc4', grade: 'mistake' }] })
    const revealed = withMoment({
      state: 'revealed',
      messages: [INTRO, { role: 'coach', text: 'The move was 2. d4.', kind: 'reveal' }],
      attempts: started.moments[0].attempts,
      best_san: 'd4',
      best_uci: 'd2d4',
    })
    const deps = fakeDeps({ getGame: vi.fn().mockResolvedValueOnce(started).mockResolvedValue(revealed) })
    renderApp(deps, '/games/game-1')
    fireEvent.click(await screen.findByRole('tab', { name: /Critical moments/ }))

    fireEvent.click(screen.getByRole('button', { name: 'Show me' }))

    expect(await screen.findByText(/The engine's move:/)).toHaveTextContent('2. d4')
    expect(screen.getByRole('button', { name: '2. Bc4' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '2. d4' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Live engine' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Critical moments \(1\/1\)/ })).toBeInTheDocument()
    expect(deps.api.momentReveal).toHaveBeenCalledWith('game-1', 1, expect.objectContaining({ fen: BEFORE_NF3 }), expect.any(Function))
  })

  test('leaving the tab pauses the moment and unlocks the board', async () => {
    const deps = fakeDeps({ getGame: vi.fn(async () => withMoment({ state: 'intro', messages: [INTRO] })) })
    renderApp(deps, '/games/game-1')
    await openMoments()

    fireEvent.click(screen.getByRole('tab', { name: 'Coach' }))

    expect(screen.getByRole('region', { name: 'Live engine' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous move (←)' })).toBeEnabled()
    expect(screen.getByLabelText('Your question')).toBeInTheDocument()
  })
})
