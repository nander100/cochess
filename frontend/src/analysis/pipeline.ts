import type { ApiClient } from '../api/client'
import type {
  CreateGameRequest,
  CreateGameResponse,
  EngineConfig,
  EngineResult,
  VerifyResponse,
} from '../api/types'
import { analyzeAll, itemsForFens, moveNumber, scanItems } from '../engine/runner'
import type { EngineBuild, EngineHandle } from '../engine/StockfishEngine'

export type AnalysisStatus =
  | { phase: 'starting' }
  | { phase: 'scanning'; done: number; total: number; moveNumber: number; totalMoves: number }
  | { phase: 'verifying'; done: number; total: number }

export interface AnalysisRun {
  game: CreateGameResponse
  engine: { build: EngineBuild; threads: number }
  config: EngineConfig
  scan: EngineResult[]
  verify: EngineResult[]
  scanMs: number
  verifyMs: number
  outcome: VerifyResponse
}

export interface PipelineDeps {
  api: ApiClient
  getEngine(config: EngineConfig): Promise<EngineHandle>
  now?: () => number
}

/** The v1 analysis flow (SPEC §3 steps 4–7): validate, scan, pick positions, verify. */
export async function runAnalysis(
  deps: PipelineDeps,
  request: CreateGameRequest,
  onStatus: (status: AnalysisStatus) => void,
): Promise<AnalysisRun> {
  const now = deps.now ?? (() => performance.now())
  onStatus({ phase: 'starting' })
  const [game, config] = await Promise.all([deps.api.createGame(request), deps.api.engineConfig()])
  const engine = await deps.getEngine(config)
  await engine.newGame()

  const totalMoves = moveNumber(game.positions.length)
  const scanStart = now()
  const scan = await analyzeAll(engine, scanItems(game), 'scan', config.scan, (done, total, item) =>
    onStatus({
      phase: 'scanning',
      done,
      total,
      moveNumber: Math.min(moveNumber(item?.ply ?? game.positions.length), totalMoves),
      totalMoves,
    }),
  )
  const scanMs = now() - scanStart
  const { verify_fens } = await deps.api.submitScan(game.game_id, scan)

  const verifyStart = now()
  const verify = await analyzeAll(
    engine,
    itemsForFens(game, verify_fens),
    'verify',
    config.verify,
    (done, total) => onStatus({ phase: 'verifying', done, total }),
  )
  const verifyMs = now() - verifyStart
  const outcome = await deps.api.submitVerify(game.game_id, verify)

  return {
    game,
    engine: { build: engine.build, threads: engine.threads },
    config,
    scan,
    verify,
    scanMs,
    verifyMs,
    outcome,
  }
}

export function statusLabel(status: AnalysisStatus): string {
  switch (status.phase) {
    case 'starting':
      return 'Loading the chess engine…'
    case 'scanning':
      return `Analyzing move ${status.moveNumber} of ${status.totalMoves}…`
    case 'verifying':
      return `Double-checking key moments (${Math.min(status.done + 1, status.total)} of ${status.total})…`
  }
}
