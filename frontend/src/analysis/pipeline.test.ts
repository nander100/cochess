import { ApiError } from '../api/client'
import { GAME, fakeDeps } from '../test/fakes'
import { type AnalysisStatus, runAnalysis, statusLabel } from './pipeline'

const REQUEST = { pgn: '1. e4 e5 2. Nf3 *', user_color: 'white' as const, elo: 1200, playstyle: null }

test('scans every position, then verifies exactly the positions the backend picks', async () => {
  const deps = fakeDeps()

  const run = await runAnalysis(deps, REQUEST, () => {})

  expect(deps.api.createGame).toHaveBeenCalledWith(REQUEST)
  expect(deps.engine.newGame).toHaveBeenCalledOnce()
  expect(run.scan.map((r) => [r.fen, r.ply, r.tier])).toEqual([
    ['fen-0 w', 1, 'scan'],
    ['fen-1 b', 2, 'scan'],
    ['fen-2 w', 3, 'scan'],
    ['fen-3 b', 4, 'scan'],
  ])
  expect(deps.api.submitScan).toHaveBeenCalledWith('game-1', run.scan)
  expect(run.verify.map((r) => [r.fen, r.ply, r.tier])).toEqual([
    ['fen-1 b', 2, 'verify'],
    ['fen-2 w', 3, 'verify'],
  ])
  expect(deps.api.submitVerify).toHaveBeenCalledWith('game-1', run.verify)
  expect(run.engine).toEqual({ build: 'stockfish-19-lite', threads: 3 })
  expect([run.scanMs, run.verifyMs]).toEqual([1000, 1000])
})

test('reports progress through each phase', async () => {
  const statuses: AnalysisStatus[] = []

  await runAnalysis(fakeDeps(), REQUEST, (status) => statuses.push(status))

  expect(statuses.map(statusLabel)).toEqual([
    'Loading the chess engine…',
    'Analyzing move 1 of 2…',
    'Analyzing move 1 of 2…',
    'Analyzing move 2 of 2…',
    'Analyzing move 2 of 2…',
    'Analyzing move 2 of 2…',
    'Double-checking key moments (1 of 2)…',
    'Double-checking key moments (2 of 2)…',
    'Double-checking key moments (2 of 2)…',
  ])
})

test('an invalid PGN fails before the engine runs', async () => {
  const deps = fakeDeps({
    createGame: vi.fn(async () => {
      throw new ApiError(422, 'Move 2 (White): Ke3 is not a legal move in that position.')
    }),
  })

  await expect(runAnalysis(deps, REQUEST, () => {})).rejects.toThrow('Ke3 is not a legal move')
  expect(deps.engine.analyze).not.toHaveBeenCalled()
})

test('a game ending in mate is scanned without its final position', async () => {
  const deps = fakeDeps({ createGame: vi.fn(async () => ({ ...GAME, final_is_terminal: true })) })

  const run = await runAnalysis(deps, REQUEST, () => {})

  expect(run.scan.map((r) => r.fen)).not.toContain('fen-3 b')
})
