import type { PipelineDeps } from '../analysis/pipeline'
import type { ApiClient } from '../api/client'
import type { CoachEvent } from '../api/sse'
import type { CreateGameResponse, EngineConfig, EngineResult, Profile } from '../api/types'
import type { EngineHandle } from '../engine/StockfishEngine'

const TIER = { multipv: 1, min_time_ms: 1, min_depth: 1, hard_cap_ms: 1, max_line_plies: 1 }
export const ENGINE_CONFIG: EngineConfig = {
  max_threads: 4,
  hash_mb: 64,
  scan: TIER,
  verify: { ...TIER, multipv: 4, max_line_plies: 10 },
  deep: { ...TIER, multipv: 4, max_line_plies: 10 },
}

export const PROFILE: Profile = {
  name: 'Alex',
  elo: 1350,
  time_control: 'rapid',
  playstyle: null,
  complete: true,
}

export const SYNOPSIS_TEXT = '### Overall\nA tidy game.\n\n### Your turn\nWhat would you try on move 2?'

export const GAME: CreateGameResponse = {
  game_id: 'game-1',
  positions: [
    { ply: 1, fen_before: 'fen-0 w', san: 'e4', uci: 'e2e4', clock_s: null },
    { ply: 2, fen_before: 'fen-1 b', san: 'e5', uci: 'e7e5', clock_s: null },
    { ply: 3, fen_before: 'fen-2 w', san: 'Nf3', uci: 'g1f3', clock_s: null },
  ],
  final_fen: 'fen-3 b',
  final_is_terminal: false,
}

export function fakeEngine(): EngineHandle {
  return {
    build: 'stockfish-19-lite',
    threads: 3,
    newGame: vi.fn(async () => {}),
    analyze: vi.fn(
      async (item, tier): Promise<EngineResult> => ({
        ply: item.ply,
        fen: item.fen,
        tier,
        depth: 14,
        time_ms: 260,
        lines: [{ rank: 1, eval_cp: 25, mate: null, moves_uci: ['e2e4'] }],
      }),
    ),
  }
}

export function fakeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    redeem: vi.fn(async () => {}),
    logout: vi.fn(async () => {}),
    me: vi.fn(async () => PROFILE),
    updateMe: vi.fn(async (update) => ({ ...PROFILE, ...update, complete: true })),
    createGame: vi.fn(async () => GAME),
    engineConfig: vi.fn(async () => ENGINE_CONFIG),
    submitScan: vi.fn(async () => ({ verify_fens: ['fen-1 b', 'fen-2 w'] })),
    submitVerify: vi.fn(async () => ({ summary_ready: false, counts: null, accuracy: null })),
    streamSynopsis: vi.fn(async (_gameId: string, onEvent: (event: CoachEvent) => void) => {
      onEvent({ type: 'status', message: 'Coach is writing…' })
      onEvent({ type: 'text', text: SYNOPSIS_TEXT })
      onEvent({ type: 'done', invalid_moves_removed: [] })
    }),
    sendChat: vi.fn(async (_gameId: string, _message: string, onEvent: (e: CoachEvent) => void) => {
      onEvent({ type: 'text', text: 'Good question.' })
      onEvent({ type: 'done', invalid_moves_removed: [] })
    }),
    submitEngineResult: vi.fn(async () => {}),
    ...overrides,
  }
}

export function fakeDeps(overrides: Partial<ApiClient> = {}): PipelineDeps & { engine: EngineHandle } {
  const engine = fakeEngine()
  let tick = 0
  return { api: fakeApi(overrides), getEngine: async () => engine, engine, now: () => (tick += 1000) }
}
