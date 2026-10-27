import type { PipelineDeps } from '../analysis/pipeline'
import type { ApiClient } from '../api/client'
import type { CoachEvent } from '../api/sse'
import { Chess } from 'chess.js'
import type {
  CreateGameResponse,
  EngineConfig,
  EngineResult,
  GameDetail,
  MoveInfo,
  Profile,
} from '../api/types'
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

/** A real game's moves with FENs from chess.js, and fake evals: 0.0 everywhere, except that
 * `mistakePly` (if given) drops White's win% to 30 and is labelled a mistake. */
export function movesFor(sans: readonly string[], mistakePly?: number): MoveInfo[] {
  const chess = new Chess()
  return sans.map((san, index) => {
    const ply = index + 1
    const fen_before = chess.fen()
    const move = chess.move(san)
    const mistake = ply === mistakePly
    return {
      ply,
      move_number: Math.floor((ply + 1) / 2),
      side: ply % 2 === 1 ? 'white' : 'black',
      san: move.san,
      uci: move.lan,
      fen_before,
      clock_s: null,
      eval_after: mistake ? '-1.0' : '0.0',
      win_pct_after: mistake ? 30 : 50,
      label: mistake ? 'mistake' : null,
    }
  })
}

const RUY = ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6']

export function finalFen(sans: readonly string[]): string {
  const chess = new Chess()
  sans.forEach((san) => chess.move(san))
  return chess.fen()
}

/** An analyzed 6-ply game (1. e4 e5 2. Nf3 Nc6 3. Bb5 a6); White's 2. Nf3 is the mistake. */
export const DETAIL: GameDetail = {
  id: 'game-1',
  status: 'analyzed',
  user_color: 'white',
  elo: 1350,
  played_at: '2026-10-01T18:04:05Z',
  info: {
    white: 'Alex',
    black: 'Rival',
    result: '1-0',
    time_control: '600+5',
    opening: 'Ruy Lopez',
    num_moves: 3,
  },
  moves: movesFor(RUY, 3),
  start_win_pct: 50,
  final_fen: finalFen(RUY),
  final_is_terminal: false,
  accuracy: { user: 81.2, opponent: 77.5 },
  counts: { inaccuracies: 0, mistakes: 1, blunders: 0, missed_mates: 0 },
  engine_results: [
    {
      fen: movesFor(RUY)[2].fen_before,
      tier: 'verify',
      depth: 18,
      lines: [{ rank: 1, eval: '+0.3', win_pct: 52.8, moves_uci: ['g1f3'], moves_san: ['Nf3'] }],
    },
  ],
  verify_fens: [],
  synopsis: null,
  chat: [],
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
    listGames: vi.fn(async () => []),
    getGame: vi.fn(async () => DETAIL),
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
