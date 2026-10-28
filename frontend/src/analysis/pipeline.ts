import type { ApiClient } from '../api/client'
import type {
  CreateGameRequest,
  CreateGameResponse,
  EngineConfig,
  EngineResult,
  GameDetail,
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

/** Upload a game, then analyze it (SPEC §3 steps 4–7): validate, scan, pick positions, verify. */
export async function runAnalysis(
  deps: PipelineDeps,
  request: CreateGameRequest,
  onStatus: (status: AnalysisStatus) => void,
): Promise<AnalysisRun> {
  onStatus({ phase: 'starting' })
  const [game, config] = await Promise.all([deps.api.createGame(request), deps.api.engineConfig()])
  return analyzeGame(deps, game, config, onStatus)
}

/**
 * Run the engine on an uploaded game: scan every position, then verify the ones the backend picks.
 * With `pendingVerify` (the game's scan is already stored, e.g. the tab was closed mid-analysis),
 * only the verify step runs. Callers show the "starting" status while the engine loads.
 */
export async function analyzeGame(
  deps: PipelineDeps,
  game: CreateGameResponse,
  config: EngineConfig,
  onStatus: (status: AnalysisStatus) => void,
  pendingVerify: readonly string[] | null = null,
): Promise<AnalysisRun> {
  const now = deps.now ?? (() => performance.now())
  const engine = await deps.getEngine(config)
  await engine.newGame()

  let scan: EngineResult[] = []
  let scanMs = 0
  let verifyFens = pendingVerify
  if (verifyFens === null) {
    const totalMoves = moveNumber(game.positions.length)
    const scanStart = now()
    scan = await analyzeAll(engine, scanItems(game), 'scan', config.scan, (done, total, item) =>
      onStatus({
        phase: 'scanning',
        done,
        total,
        moveNumber: Math.min(moveNumber(item?.ply ?? game.positions.length), totalMoves),
        totalMoves,
      }),
    )
    scanMs = now() - scanStart
    verifyFens = (await deps.api.submitScan(game.game_id, scan)).verify_fens
  }

  const verifyStart = now()
  const verify = await analyzeAll(
    engine,
    itemsForFens(game, verifyFens),
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

/** Finish analyzing a game already uploaded (e.g. the tab closed mid-analysis, or an onboarding
 * game queued for analysis): the whole run, or just the verify step if its scan is stored. */
export function resumeGame(
  deps: PipelineDeps,
  detail: GameDetail,
  config: EngineConfig,
  onStatus: (status: AnalysisStatus) => void,
): Promise<AnalysisRun> {
  const pending = detail.status === 'scanned' ? detail.verify_fens : null
  return analyzeGame(deps, asUploadedGame(detail), config, onStatus, pending)
}

function asUploadedGame(detail: GameDetail): CreateGameResponse {
  return {
    game_id: detail.id,
    positions: detail.moves.map(({ ply, fen_before, san, uci, clock_s }) => ({ ply, fen_before, san, uci, clock_s })),
    final_fen: detail.final_fen,
    final_is_terminal: detail.final_is_terminal,
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
