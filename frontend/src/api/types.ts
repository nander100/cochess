// TypeScript mirrors of the backend schemas (backend/app/api/schemas.py, app/analysis/engine.py).

export type Color = 'white' | 'black'
export type Tier = 'scan' | 'verify' | 'deep'

export interface Position {
  ply: number
  fen_before: string
  san: string
  uci: string
  clock_s: number | null
}

/** Elo and playstyle come from the player's profile (SPEC_V2 §4.3). */
export interface CreateGameRequest {
  pgn: string
  user_color: Color
}

export type TimeControl = 'bullet' | 'blitz' | 'rapid' | 'classical'

export interface Profile {
  name: string
  elo: number | null
  time_control: TimeControl | null
  playstyle: string | null
  /** Elo and time control are set: the player can analyze games. */
  complete: boolean
}

/** PATCH /api/me: only the fields sent change. A blank playstyle clears it. */
export interface ProfileUpdate {
  name?: string
  elo?: number
  time_control?: TimeControl
  playstyle?: string
}

export interface CreateGameResponse {
  game_id: string
  positions: Position[]
  final_fen: string
  final_is_terminal: boolean
}

export interface TierConfig {
  multipv: number
  min_time_ms: number
  min_depth: number
  hard_cap_ms: number
  max_line_plies: number
}

export interface EngineConfig {
  max_threads: number
  hash_mb: number
  scan: TierConfig
  verify: TierConfig
  deep: TierConfig
  /** The live engine panel: shown only, never posted. */
  live: TierConfig
}

/** One engine line. Scores are from White's point of view; exactly one of eval_cp / mate is set. */
export interface EngineLine {
  rank: number
  eval_cp: number | null
  mate: number | null
  moves_uci: string[]
}

export interface EngineResult {
  ply: number | null
  fen: string
  tier: Tier
  depth: number
  time_ms: number
  lines: EngineLine[]
}

export interface ScanResponse {
  verify_fens: string[]
}

export interface Counts {
  inaccuracies: number
  mistakes: number
  blunders: number
  missed_mates: number
}

export interface Accuracy {
  user: number
  opponent: number
}

export interface VerifyResponse {
  summary_ready: boolean
  counts: Counts | null
  accuracy: Accuracy | null
}

// GET /api/games and GET /api/games/{id} (backend/app/api/schemas.py).

export type GameStatus = 'uploaded' | 'scanned' | 'analyzed'
export type UserResult = 'win' | 'loss' | 'draw'
export type MoveLabel = 'inaccuracy' | 'mistake' | 'blunder' | 'missed_mate'

export interface GameListItem {
  id: string
  played_at: string
  opponent: string
  user_color: Color
  user_result: UserResult | null
  time_control: string | null
  opening: string | null
  accuracy: number | null
  status: GameStatus
}

export interface MoveInfo {
  ply: number
  move_number: number
  side: Color
  san: string
  uci: string
  fen_before: string
  clock_s: number | null
  /** Display format, "+0.3" / "-M2"; null until the engine has run. */
  eval_after: string | null
  /** White's win% after the move, 0..100. */
  win_pct_after: number | null
  label: MoveLabel | null
}

export interface StoredLine {
  rank: number
  eval: string
  /** White's win%, 0..100 (computed by the backend). */
  win_pct: number
  moves_uci: string[]
  moves_san: string[]
}

export interface StoredEngineResult {
  fen: string
  tier: Tier
  depth: number
  lines: StoredLine[]
}

export interface GameInfo {
  white: string
  black: string
  result: string
  time_control: string | null
  opening: string | null
  num_moves: number
}

export interface ChatEntry {
  role: 'player' | 'coach'
  text: string
}

export interface GameDetail {
  id: string
  status: GameStatus
  user_color: Color
  elo: number
  played_at: string
  info: GameInfo
  moves: MoveInfo[]
  start_win_pct: number | null
  final_fen: string
  final_is_terminal: boolean
  accuracy: Accuracy | null
  counts: Counts | null
  engine_results: StoredEngineResult[]
  /** While status is "scanned": the positions still to verify. */
  verify_fens: string[]
  synopsis: { text: string; invalid_moves_removed: string[] } | null
  chat: ChatEntry[]
}
