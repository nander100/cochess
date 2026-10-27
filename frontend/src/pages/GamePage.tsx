import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router'
import { type ChatDeps, type ChatProgress, askCoach, explainPosition } from '../analysis/chat'
import { type AnalysisRun, type AnalysisStatus, type PipelineDeps, analyzeGame, statusLabel } from '../analysis/pipeline'
import { ApiError, isLoggedOut } from '../api/client'
import type { CreateGameResponse, EngineResult, GameDetail } from '../api/types'
import { Board, type BoardMove } from '../board/Board'
import { EnginePanel, type LiveEngine } from '../board/EnginePanel'
import { EvalBar } from '../board/EvalBar'
import { EvalGraph, type GraphPoint } from '../board/EvalGraph'
import { MoveList } from '../board/MoveList'
import {
  type GameTree,
  ROOT,
  type TreeNode,
  addMove,
  fromMoves,
  lineFrom,
  next,
  pathTo,
  positionLabel,
  previous,
} from '../board/tree'
import { useArrowKeys } from '../board/useArrowKeys'
import { ChatPanel } from '../components/ChatPanel'
import { EngineStats } from '../components/EngineStats'
import { ProgressBar } from '../components/ProgressBar'
import { Synopsis, type SynopsisState } from '../components/Synopsis'
import { type LiveLine, isGameOver } from '../engine/live'
import { analyzeAll } from '../engine/runner'
import { errorText, gameDate } from './util'

interface GamePageProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

/** Navigation state from the upload page: this session's engine run, to show its details. */
export interface FreshAnalysis {
  run: AnalysisRun
}

type Load = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; detail: GameDetail }

/** One game on the analysis board, loaded from the database (SPEC_V2 §5.1). */
export function GamePage({ deps, onLoggedOut }: GamePageProps) {
  const { gameId = '' } = useParams()
  const fresh = (useLocation().state as FreshAnalysis | null)?.run ?? null
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  const reload = useCallback(() => {
    deps.api.getGame(gameId).then(
      (detail) => setLoad({ kind: 'ready', detail }),
      (error: unknown) => {
        if (isLoggedOut(error)) onLoggedOut()
        else if (error instanceof ApiError && error.status === 404) {
          setLoad({ kind: 'error', message: "That game doesn't exist, or it isn't yours." })
        } else setLoad({ kind: 'error', message: errorText(error) })
      },
    )
  }, [deps, gameId, onLoggedOut])

  useEffect(reload, [reload])

  if (load.kind === 'loading') return <p className="coach-writing">Loading the game…</p>
  if (load.kind === 'error') {
    return (
      <p className="run-error" role="alert">
        {load.message}
      </p>
    )
  }
  return (
    <AnalysisBoard
      key={`${load.detail.id}-${load.detail.status}`}
      detail={load.detail}
      deps={deps}
      fresh={fresh}
      onLoggedOut={onLoggedOut}
      onAnalyzed={reload}
    />
  )
}

interface AnalysisBoardProps {
  detail: GameDetail
  deps: PipelineDeps
  fresh: AnalysisRun | null
  onLoggedOut: () => void
  onAnalyzed: () => void
}

function AnalysisBoard({ detail, deps, fresh, onLoggedOut, onAnalyzed }: AnalysisBoardProps) {
  const [tree, setTree] = useState<GameTree>(() => fromMoves(detail.moves, detail.final_fen))
  const [current, setCurrent] = useState(ROOT)
  const node = tree.nodes[current]
  const stored = useMemo(() => storedByPosition(detail), [detail])

  const [engineOn, setEngineOn] = useState(false)
  const [live, setLive] = useState<{ fen: string; line: LiveLine } | null>(null)
  const engine = useRef<Promise<LiveEngine> | null>(null)
  // The browser engine and tier settings, loaded once and shared by the live panel and the chat.
  const loadEngine = useCallback((): Promise<LiveEngine> => {
    engine.current ??= deps.api.engineConfig().then(async (config) => ({ config, engine: await deps.getEngine(config) }))
    engine.current.catch(() => {
      engine.current = null // let the next attempt retry
    })
    return engine.current
  }, [deps])

  // Positions the backend has verify or deep lines for; chat and Explain analyze others first.
  const [analyzed, setAnalyzed] = useState(
    () => new Set(detail.engine_results.filter((r) => r.tier !== 'scan').map((r) => positionKey(r.fen))),
  )
  const ensureAnalyzed = useCallback(
    async (fen: string, onProgress: (progress: ChatProgress) => void): Promise<EngineResult | null> => {
      if (analyzed.has(positionKey(fen)) || isGameOver(fen)) return null
      onProgress('looking')
      const { engine: handle, config } = await loadEngine()
      const result = await handle.analyze({ fen, ply: null }, 'verify', config.verify)
      setAnalyzed((keys) => new Set(keys).add(positionKey(fen)))
      return result
    },
    [analyzed, loadEngine],
  )

  const back = useCallback(() => setCurrent((id) => previous(tree, id)), [tree])
  const forward = useCallback(() => setCurrent((id) => next(tree, id)), [tree])
  useArrowKeys(back, forward)

  function play(move: BoardMove) {
    const result = addMove(tree, current, move)
    if (!result) return // chessground only offers legal moves; nothing to do otherwise
    setTree(result.tree)
    setCurrent(result.nodeId)
  }

  const evaluation =
    engineOn && live?.fen === node.fen
      ? { winPct: live.line.winPct, evalText: live.line.evalText }
      : positionEval(node, detail, stored)
  const points = graphPoints(detail)
  return (
    <section className="analysis" aria-label="Analysis board">
      <GameHeading detail={detail} />
      {detail.status !== 'analyzed' && (
        <ResumeAnalysis detail={detail} deps={deps} onLoggedOut={onLoggedOut} onDone={onAnalyzed} />
      )}
      <div className="analysis-grid">
        <div className="board-column">
          <div className="board-row">
            <EvalBar winPct={evaluation.winPct} evalText={evaluation.evalText} orientation={detail.user_color} />
            <Board
              fen={node.fen}
              orientation={detail.user_color}
              lastMove={node.uci}
              movable
              onMove={play}
            />
          </div>
          <div className="board-controls" role="group" aria-label="Move navigation">
            <button type="button" onClick={() => setCurrent(ROOT)} aria-label="Start of the game">
              ⏮
            </button>
            <button type="button" onClick={back} aria-label="Previous move (←)">
              ◀
            </button>
            <button type="button" onClick={forward} aria-label="Next move (→)">
              ▶
            </button>
            <button type="button" onClick={() => setCurrent(endOfLine(tree, current))} aria-label="End of the line">
              ⏭
            </button>
          </div>
          {points.length > 1 && (
            <EvalGraph
              points={points}
              userColor={detail.user_color}
              currentPly={branchPly(tree, node)}
              onSelectPly={(ply) => setCurrent(mainlineNode(tree, ply))}
            />
          )}
          <EnginePanel fen={node.fen} enabled={engineOn} onToggle={setEngineOn} load={loadEngine} onBest={setLive} />
          {fresh && <EngineStats run={fresh} />}
        </div>
        <div className="side-column">
          <div className="panel">
            <h2 className="panel-title">Moves</h2>
            <MoveList tree={tree} current={current} userColor={detail.user_color} onSelect={setCurrent} />
          </div>
          {detail.status === 'analyzed' && (
            <Coach
              detail={detail}
              deps={deps}
              board={node}
              ensureAnalyzed={ensureAnalyzed}
              loadEngine={loadEngine}
              autoSynopsis={fresh !== null}
              onLoggedOut={onLoggedOut}
            />
          )}
        </div>
      </div>
    </section>
  )
}

function GameHeading({ detail }: { detail: GameDetail }) {
  const { info, accuracy } = detail
  const date = gameDate(detail.played_at)
  return (
    <header className="game-heading">
      <h2>
        {info.white} – {info.black} <span className="result">{info.result}</span>
      </h2>
      <p>
        {date}
        {info.time_control && ` · ${info.time_control}`}
        {info.opening && ` · ${info.opening}`} · you played {detail.user_color}
        {accuracy?.user != null && ` · your accuracy ${accuracy.user}%`}
      </p>
    </header>
  )
}

/** An analysis that didn't finish (the tab was closed): pick it up from where the server says. */
function ResumeAnalysis({ detail, deps, onLoggedOut, onDone }: {
  detail: GameDetail
  deps: PipelineDeps
  onLoggedOut: () => void
  onDone: () => void
}) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function resume() {
    setError(null)
    setStatus({ phase: 'starting' })
    try {
      const config = await deps.api.engineConfig()
      const pending = detail.status === 'scanned' ? detail.verify_fens : null
      await analyzeGame(deps, asUploadedGame(detail), config, setStatus, pending)
      onDone()
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
      setStatus(null)
    }
  }

  return (
    <div className="resume" role="region" aria-label="Unfinished analysis">
      {status ? (
        <ProgressBar label={statusLabel(status)} {...(status.phase === 'starting' ? { done: 0, total: 1 } : status)} />
      ) : (
        <>
          <p>The engine hasn't finished analyzing this game.</p>
          <button type="button" onClick={() => void resume()}>
            Resume analysis
          </button>
        </>
      )}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

/** The synopsis and the chat, for an analyzed game. */
function Coach({ detail, deps, board, ensureAnalyzed, loadEngine, autoSynopsis, onLoggedOut }: {
  detail: GameDetail
  deps: PipelineDeps
  /** The position on the board: chat and Explain are about it (SPEC_V2 §6). */
  board: TreeNode
  ensureAnalyzed: (fen: string, onProgress: (progress: ChatProgress) => void) => Promise<EngineResult | null>
  loadEngine: () => Promise<LiveEngine>
  autoSynopsis: boolean
  onLoggedOut: () => void
}) {
  const [synopsis, setSynopsis] = useState<SynopsisState | null>(
    detail.synopsis ? { status: 'done', text: detail.synopsis.text, error: null } : null,
  )
  const started = useRef(false)

  const write = useCallback(async () => {
    setSynopsis({ status: 'writing', text: '', error: null })
    let text = ''
    let finished = false
    try {
      await deps.api.streamSynopsis(detail.id, (event) => {
        if (event.type === 'text') {
          text += event.text
          setSynopsis({ status: 'writing', text, error: null })
        } else if (event.type === 'done' || event.type === 'error') {
          finished = true
          const error = event.type === 'error' ? event.message : null
          setSynopsis({ status: error ? 'error' : 'done', text, error })
        }
      })
      if (!finished) setSynopsis({ status: 'error', text, error: 'The connection to the coach was lost.' })
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setSynopsis({ status: 'error', text, error: errorText(caught) })
    }
  }, [deps, detail.id, onLoggedOut])

  // Right after an upload the synopsis starts on its own, as in v1; StrictMode-safe.
  useEffect(() => {
    if (autoSynopsis && !detail.synopsis && !started.current) {
      started.current = true
      void write()
    }
  }, [autoSynopsis, detail.synopsis, write])

  const chatDeps: ChatDeps = {
    api: deps.api,
    async analyzeDeep(positions) {
      const { engine, config } = await loadEngine()
      return analyzeAll(engine, positions.map((p) => ({ fen: p.fen, ply: null })), 'deep', config.deep)
    },
  }

  return (
    <>
      {synopsis ? (
        <Synopsis state={synopsis} onRetry={() => void write()} />
      ) : (
        <section className="synopsis" aria-label="Coach's synopsis">
          <h2>Your coach</h2>
          <button type="button" onClick={() => void write()}>
            Write a synopsis of this game
          </button>
        </section>
      )}
      <ChatPanel
        initial={detail.chat}
        where={positionLabel(board)}
        ask={async (message, onProgress) => {
          const position = await positionRequest(board, ensureAnalyzed, onProgress)
          return askCoach(chatDeps, detail.id, { message, ...position }, onProgress)
        }}
        explain={async (onProgress) => {
          const position = await positionRequest(board, ensureAnalyzed, onProgress)
          return explainPosition(chatDeps, detail.id, position, onProgress)
        }}
      />
    </>
  )
}

/** The board position for the backend: its UCI path, plus the browser's verify result when the
 * backend has no lines for it yet. */
async function positionRequest(
  node: TreeNode,
  ensureAnalyzed: (fen: string, onProgress: (progress: ChatProgress) => void) => Promise<EngineResult | null>,
  onProgress: (progress: ChatProgress) => void,
): Promise<{ path_uci: string[]; engine_result?: EngineResult }> {
  const result = await ensureAnalyzed(node.fen, onProgress)
  return { path_uci: pathTo(node.id), ...(result ? { engine_result: result } : {}) }
}

/** The game as POST /api/games returned it, for the engine pipeline. */
function asUploadedGame(detail: GameDetail): CreateGameResponse {
  return {
    game_id: detail.id,
    positions: detail.moves.map(({ ply, fen_before, san, uci, clock_s }) => ({ ply, fen_before, san, uci, clock_s })),
    final_fen: detail.final_fen,
    final_is_terminal: detail.final_is_terminal,
  }
}

/** A position's identity for matching stored engine results: FEN without the move counters. */
function positionKey(fen: string): string {
  return fen.split(' ').slice(0, 4).join(' ')
}

function storedByPosition(detail: GameDetail): Map<string, GameDetail['engine_results'][number]> {
  return new Map(detail.engine_results.map((result) => [positionKey(result.fen), result]))
}

/** What the eval bar shows for the position on the board. */
function positionEval(
  node: TreeNode,
  detail: GameDetail,
  stored: Map<string, GameDetail['engine_results'][number]>,
): { winPct: number | null; evalText: string | null } {
  if (node.mainline && node.id !== ROOT) return { winPct: node.winPctAfter, evalText: node.evalAfter }
  const best = stored.get(positionKey(node.fen))?.lines[0]
  if (node.id === ROOT) return { winPct: detail.start_win_pct, evalText: best?.eval ?? null }
  return { winPct: best?.win_pct ?? null, evalText: best?.eval ?? null }
}

function graphPoints(detail: GameDetail): GraphPoint[] {
  if (detail.start_win_pct === null) return []
  const start: GraphPoint = { ply: 0, winPct: detail.start_win_pct, evalText: null, moveText: null, label: null, side: null }
  return [
    start,
    ...detail.moves.flatMap((move) =>
      move.win_pct_after === null
        ? []
        : [
            {
              ply: move.ply,
              winPct: move.win_pct_after,
              evalText: move.eval_after,
              moveText: `${move.move_number}${move.side === 'white' ? '.' : '...'} ${move.san}`,
              label: move.label,
              side: move.side,
            },
          ],
    ),
  ]
}

/** The mainline ply the position belongs to: its own, or where its variation left the game. */
function branchPly(tree: GameTree, node: TreeNode): number {
  let walker: TreeNode | undefined = node
  while (walker && !walker.mainline) walker = walker.parent === null ? undefined : tree.nodes[walker.parent]
  return walker?.ply ?? 0
}

function mainlineNode(tree: GameTree, ply: number): string {
  const line = lineFrom(tree, ROOT)
  return line[Math.min(ply, line.length - 1)].id
}

function endOfLine(tree: GameTree, nodeId: string): string {
  const line = lineFrom(tree, nodeId)
  return line[line.length - 1].id
}
