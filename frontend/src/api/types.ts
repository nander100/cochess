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
  time_control_category: TimeControl | 'correspondence' | null
  moments_total: number
  moments_done: number
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
  /** That position's UCI path; a coach answer has its question's path. Null for v1 chats. */
  path_uci?: string[] | null
  /** A coach answer's board tags (SPEC_V3 §6). */
  annotations?: Annotation[]
  moves?: MoveToken[]
  line_links?: LineLink[]
}

/** The coach's colors for arrows and highlights (SPEC_V3 §6.1). */
export type AnnotationColor = 'green' | 'red' | 'yellow' | 'blue'

/** One checked board tag from a coach message: drawn on the position the message is about. Its
 * placeholder link `cc:board/{tag_index}` starts at `char_offset` in the message's text. */
export interface Annotation {
  tag_index: number
  char_offset: number
  arrows: { orig: string; dest: string; color: AnnotationColor }[]
  squares: { square: string; color: AnnotationColor }[]
}

/** A request for a line walkthrough (SPEC_V3 §7.2): the start, the line (UCI, at most 10 plies)
 * and the browser's scan of each position along it (empty to ask for a cached walkthrough). */
export interface WalkthroughRequest {
  start_path_uci: string[]
  line_uci: string[]
  step_results: EngineResult[]
}

export interface WalkthroughStep {
  index: number
  uci: string
  san: string
  fen_after: string
  /** "+0.8", White's point of view; null when the step wasn't evaluated. */
  eval_after: string | null
  /** White's win%, for the eval bar. */
  win_pct_after: number | null
  text: string
  /** Arrows and highlights on the position after this step's move. */
  annotation: Annotation | null
  /** The text's move tags (SPEC_V3 §9.4). */
  moves?: MoveToken[]
}

/** A line explained step by step by the coach. */
export interface Walkthrough {
  start_path_uci: string[]
  line_uci: string[]
  start_fen: string
  intro: string
  steps: WalkthroughStep[]
  summary: string
  invalid_moves_removed: string[]
  intro_moves?: MoveToken[]
  summary_moves?: MoveToken[]
}

/** A move tag (SPEC_V3 §9.4): the backend's words for a validated move. Its placeholder link
 * `cc:move/{index}` is in the text; it shows as words, notation, or both by detail level. */
export interface MoveToken {
  index: number
  char_offset: number
  san: string
  words: string
  move_number: number | null
  white: boolean | null
  /** Its words begin a sentence: shown capitalized. */
  sentence_start?: boolean
}

/** A line link (SPEC_V3 §9.4): a line from the data, played on the board when clicked. */
export interface LineLink {
  index: number
  char_offset: number
  line_id: string
  ref: string
  label: string
  kind: 'engine' | 'refutation' | 'candidate' | 'best' | 'variation'
  start_path_uci: string[]
  moves_uci: string[]
}

/** A recommended puzzle theme (SPEC_V3 §8.2): a chip linking to Lichess's puzzle trainer. */
export interface PuzzleToken {
  index: number
  char_offset: number
  theme: string
  label: string
  url: string
}

/** A coach message's structured parts, tied to `cc:` placeholders in its text. */
export interface MessageTokens {
  moves?: MoveToken[]
  line_links?: LineLink[]
  annotations?: Annotation[]
  puzzles?: PuzzleToken[]
}

/** A coach answer: its text (tags as `cc:` placeholder links) and their tokens. */
export interface CoachReply extends MessageTokens {
  text: string
  annotations: Annotation[]
}

/** Where a linked line's playback stops and why (SPEC_V3 §9.6), decided by the backend. */
export interface Playback {
  line_id: string
  start_fen: string
  moves_uci: string[]
  moves_san: string[]
  evals: (string | null)[]
  win_pcts: (number | null)[]
  settle_ply: number
  caption: string
}

/** How the coach writes and how moves are shown (SPEC_V3 §9.3). */
export type DetailLevel = 'plain' | 'standard' | 'technical'

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
  /** A coach message's board tags, on the moment's position (SPEC_V3 §6). */
  annotations?: Annotation[]
  moves?: MoveToken[]
  line_links?: LineLink[]
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
  /** Failed tries before the answer is shown (the "Tries left" dots). */
  max_attempts: number
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
  synopsis: ({ text: string; invalid_moves_removed: string[] } & MessageTokens) | null
  chat: ChatEntry[]
  moments: MomentInfo[]
  /** The saved variations in display order, or null if they were never saved (SPEC_V3 §5.1). */
  variations?: SavedVariation[] | null
}

/** A line the player explored: where it starts and its moves, both UCI (SPEC_V3 §5.1). */
export interface SavedVariation {
  start_path: string[]
  moves: string[]
}

/** An exported game, ready to download (SPEC_V3 §5.2). */
export interface PgnExport {
  filename: string
  text: string
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
  moves?: MoveToken[]
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

/** GET /api/tendencies (SPEC_V2 §9; backend app/analysis/tendencies.py). */
export type Trend = 'improving' | 'worsening' | 'steady'

export interface Tendency {
  theme: string
  label: string
  rate_per_game: number
  score: number
  trend: Trend | null
  games_seen: number
  provisional: boolean
  recent_example: { game_id: string; move_number: number | null; move_san: string | null }
}

export interface TendencyReport {
  games_analyzed: number
  provisional: boolean
  tendencies: Tendency[]
  accuracy: {
    overall: number | null
    by_color: Record<Color, number | null>
    by_phase: Record<string, number | null>
  }
}

/** GET / PATCH /api/settings (SPEC_V3 §4.3). */
export type BoardScheme = 'blue' | 'pale' | 'soft'
export type PieceSet = 'cburnett' | 'merida'

export interface UserSettings {
  theme: 'light' | 'dark' | 'system'
  board_scheme: BoardScheme
  piece_set: PieceSet
  sounds: boolean
  engine_panel: boolean
  /** "auto" follows the rating band; `effective_detail_level` is what that means now. */
  coach_detail_level: DetailLevel | 'auto'
  effective_detail_level: DetailLevel
  /** Line playback: one move every this many seconds, 0.75 to 3 (SPEC_V3 §9.5). */
  playback_seconds: number
}

/** The dashboard (SPEC_V3 §8.1), one response from GET /api/dashboard. */
export type DashboardRange = '10' | '25' | 'all'

export interface DashboardFilters {
  tc: TimeControl | null
  color: Color | null
  range: DashboardRange
}

export interface PuzzleLink {
  theme: string
  label: string
  url: string
}

export interface FocusArea {
  theme: string
  label: string
  trend: 'improving' | 'worsening' | 'steady' | null
  rate_per_game: number
  games_seen: number
  example_game_id: string | null
  example_move: string | null
  example_ply: number | null
  puzzles: PuzzleLink[]
}

export interface Dashboard {
  games: number
  focus_areas: FocusArea[]
  continue_games: { game_id: string; opponent: string; played_at: string; moments_total: number; moments_done: number }[]
  mistake_trend: {
    themes: { theme: string; label: string }[]
    points: { games_analyzed: number; date: string; rates: Record<string, number> }[]
  }
  accuracy: {
    points: {
      game_id: string
      played_at: string
      color: Color
      result: UserResult | null
      accuracy: number
      rolling: number
    }[]
    by_phase: Record<'opening' | 'middlegame' | 'endgame', number | null>
  }
  recent: {
    game_id: string
    played_at: string
    opponent: string
    color: Color
    result: UserResult | null
    accuracy: number | null
    moments_total: number
    moments_done: number
  }[]
  onboarding: { complete: boolean; analyzed: number; total: number; has_report: boolean }
}
