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
  /** Where on the board a player's message was sent from ("after 14. Nf3"); null for v1 chats. */
  where: string | null
}

/** A chat message or Explain request: the board position as UCI moves from the start
 * (SPEC_V2 §5.2), and the browser's engine result for it when the backend has none yet. */
export interface PositionRequest {
  path_uci: string[]
  engine_result?: EngineResult
}

export interface ChatRequest extends PositionRequest {
  message: string
}

/** "new" until the player opens it (SPEC_V2 §8.2). */
export type MomentState = 'new' | 'intro' | 'attempt' | 'solved' | 'revealed'
export type MomentGrade = 'best' | 'good' | 'inaccuracy' | 'mistake' | 'blunder'

export interface MomentMessage {
  role: 'player' | 'coach'
  text: string
  kind: string
}

/** A critical moment and the player's progress on it. The best move is only there once the
 * moment is solved or revealed. */
export interface MomentInfo {
  index: number
  ply: number
  move_number: number
  side: Color
  san: string
  uci: string
  label: MoveLabel
  eval_before: string
  eval_after: string
  state: MomentState
  attempts: { uci: string; san: string; grade: MomentGrade }[]
  messages: MomentMessage[]
  best_san: string | null
  best_uci: string | null
}

/** An attempt at a moment: the move, the player's reasoning, and the browser's deep searches of
 * the position before (once per moment) and after the move (not when the move ends the game). */
export interface AttemptRequest {
  move_uci: string
  reasoning?: string
  engine_before?: EngineResult
  engine_after?: EngineResult
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
  moments: MomentInfo[]
}

// Onboarding (SPEC_V2 §10), mirroring backend/app/api/onboarding_schemas.py.
export type Category = TimeControl | 'correspondence'
export type Slot = 'white_win' | 'white_loss' | 'black_win' | 'black_loss'
export type SlotReason =
  | 'invalid_pgn'
  | 'duplicate'
  | 'needs_color'
  | 'needs_time_control'
  | 'wrong_time_control'
  | 'unfinished'
  | 'draw'
  | 'slot_full'

export interface GameChoice {
  user_color?: Color | null
  time_control_category?: TimeControl | null
}

export interface ParsedRow {
  index: number
  pgn: string | null
  white: string | null
  black: string | null
  result: string | null
  date: string | null
  time_control: string | null
  category: Category | null
  error: { code: string; message: string; move_number: number | null } | null
  suggested_color: Color | null
  user_color: Color | null
  user_result: UserResult | null
  slot: Slot | null
  reason: SlotReason | null
}

export interface SlotCount {
  slot: Slot
  filled: number
  of: number
}

export interface ParseResponse {
  primary_time_control: TimeControl
  games: ParsedRow[]
  slots: SlotCount[]
}

export interface SubmitGame {
  pgn: string
  user_color: Color
  time_control_category?: TimeControl | null
}

export interface SubmitResponse {
  results: { index: number; slot: Slot | null; reason: SlotReason | null; game_id: string | null }[]
  slots: SlotCount[]
}

export interface OnboardingGame {
  id: string
  slot: Slot
  status: GameStatus
  opponent: string
  played_at: string
  opening: string | null
}

export interface BaselineReport {
  text: string
  invalid_moves_removed: string[]
  game_ids: string[]
  created_at: string
}

export interface OnboardingStatus {
  primary_time_control: TimeControl | null
  slots: SlotCount[]
  games: OnboardingGame[]
  complete: boolean
  analyzed: number
  report_ready: boolean
  report: BaselineReport | null
}
