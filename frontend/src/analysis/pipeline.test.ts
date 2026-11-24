import { ApiError } from '../api/client'
import { ENGINE_CONFIG, GAME, fakeDeps, fakeEngine } from '../test/fakes'
import { type AnalysisStatus, analyzeGame, runAnalysis, statusLabel } from './pipeline'

const REQUEST = { pgn: '1. e4 e5 2. Nf3 *', user_color: 'white' as const }

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

test('with an engine pool, scan and verify run on the pool and the main engine stays idle', async () => {
  const pool = [fakeEngine(), fakeEngine(), fakeEngine()]
  const deps = { ...fakeDeps(), getPool: vi.fn(async () => pool) }

  const run = await runAnalysis(deps, REQUEST, () => {})

  expect(run.scan.map((r) => r.ply)).toEqual([1, 2, 3, 4]) // game order, whoever searched them
  expect(run.verify.map((r) => r.ply)).toEqual([2, 3])
  expect(pool.every((engine) => vi.mocked(engine.newGame).mock.calls.length === 1)).toBe(true)
  const searched = pool.reduce((sum, engine) => sum + vi.mocked(engine.analyze).mock.calls.length, 0)
  expect(searched).toBe(6)
  expect(deps.engine.analyze).not.toHaveBeenCalled()
  expect(run.engine).toEqual({ build: 'stockfish-19-lite', threads: 3 })
})

test('a pool of one (or none) falls back to the main engine', async () => {
  const deps = { ...fakeDeps(), getPool: vi.fn(async () => null) }

  const run = await runAnalysis(deps, REQUEST, () => {})

  expect(run.scan).toHaveLength(4)
  expect(deps.engine.analyze).toHaveBeenCalledTimes(6)
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

test('resuming after the scan verifies the stored positions without scanning again', async () => {
  const deps = fakeDeps()

  const run = await analyzeGame(deps, GAME, ENGINE_CONFIG, () => {}, ['fen-2 w'])

  expect(deps.api.submitScan).not.toHaveBeenCalled()
  expect(run.scan).toEqual([])
  expect(run.verify.map((r) => [r.fen, r.ply, r.tier])).toEqual([['fen-2 w', 3, 'verify']])
  expect(deps.api.submitVerify).toHaveBeenCalledWith('game-1', run.verify)
})
