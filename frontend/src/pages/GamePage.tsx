import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'
import { type ChatDeps, type ChatProgress, askCoach, explainPosition } from '../analysis/chat'
import { BeforeSearches, type MomentDeps, fenAfter } from '../analysis/moments'
import { type AnalysisRun, type AnalysisStatus, type PipelineDeps, resumeGame, statusLabel } from '../analysis/pipeline'
import { ApiError, isLoggedOut } from '../api/client'
import type { Annotation, EngineResult, GameDetail, MomentInfo } from '../api/types'
import { Board, type BoardMove } from '../board/Board'
import { latestByPath } from '../board/coachShapes'
import { useCoachDrawings } from '../board/useCoachDrawings'
import { EnginePanel, type LiveEngine } from '../board/EnginePanel'
import { EvalBar } from '../board/EvalBar'
import { EvalGraph, type GraphPoint } from '../board/EvalGraph'
import { MoveList } from '../board/MoveList'
import { useVariationSaver } from '../board/useVariationSaver'
import { deleteVariation, fromUci, isWithin, variationMoves, promoteVariation, withLine, withVariations } from '../board/variations'
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
import { useShortcuts } from '../shortcuts/useShortcuts'
import { ChatPanel, type ShowChatTag } from '../components/ChatPanel'
import { chatMessages } from '../components/chatMessages'
import { EngineStats } from '../components/EngineStats'
import { isUnsolved } from '../moments/moment'
import { MomentStepper } from '../moments/MomentStepper'
import { WalkthroughPanel } from '../walkthrough/WalkthroughPanel'
import { useWalkthrough } from '../walkthrough/useWalkthrough'
import { WALK_MAX_PLIES } from '../analysis/walkthrough'
import { CoachSummaryHeading, Synopsis, type SynopsisState } from '../components/Synopsis'
import { type LiveLine, isGameOver } from '../engine/live'
import { analyzeAll } from '../engine/runner'
import { BoardNav, GameHeading, MovesPanel } from './AnalysisParts'
import { GameOptions } from './GameOptions'
import Markdown from 'react-markdown'
import { useSettings } from '../settings/settingsContext'
import { Button, ColorSwatch, EmptyState, ErrorState, FeatureCard, ProgressBar, Skeleton, Tabs } from '../ui'
import './GamePage.css'
import { errorText } from './util'

interface GamePageProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

/** Navigation state from the upload page: this session's engine run, to show its details. */
export interface FreshAnalysis {
  run: AnalysisRun
}

type Load =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; detail: GameDetail }

/** One game on the analysis board, loaded from the database (SPEC_V2 §5.1). */
export function GamePage({ deps, onLoggedOut }: GamePageProps) {
  const { gameId = '' } = useParams()
  const location = useLocation()
  const fresh = (location.state as FreshAnalysis | null)?.run ?? null
  // ?view=moments&moment=N opens the critical-moments view (the nav's "Critical moments").
  const [params, setParams] = useSearchParams()
  const initialTab: Tab = params.get('view') === 'moments' ? 'moments' : 'coach'
  const initialMoment = Number(params.get('moment')) || null
  const showTab = useCallback(
    (tab: Tab) => setParams(tab === 'moments' ? { view: 'moments' } : {}, { replace: true, state: location.state }),
    [setParams, location.state],
  )
  const [load, setLoad] = useState<Load>({ kind: 'loading' })
  // After a color change that needs a few positions verified, the analysis resumes on its own.
  const [autoResume, setAutoResume] = useState(false)
  const goTo = useNavigate()

  const reload = useCallback(() => {
    deps.api.getGame(gameId).then(
      (detail) => setLoad({ kind: 'ready', detail }),
      (error: unknown) => {
        if (isLoggedOut(error)) onLoggedOut()
        else if (error instanceof ApiError && error.status === 404) setLoad({ kind: 'missing' })
        else setLoad({ kind: 'error', message: errorText(error) })
      },
    )
  }, [deps, gameId, onLoggedOut])

  useEffect(reload, [reload])

  if (load.kind === 'loading') return <Skeleton lines={6} label="Loading the game…" />
  if (load.kind === 'error') return <ErrorState message={`The game couldn't be loaded. ${load.message}`} onRetry={reload} />
  if (load.kind === 'missing') {
    return (
      <div role="alert">
        <EmptyState title="That game doesn't exist, or it isn't yours." action={<Link to="/games">Go to your games</Link>}>
          <p>Check the link, or open the game from your list.</p>
        </EmptyState>
      </div>
    )
  }
  return (
    <AnalysisBoard
      key={`${load.detail.id}-${load.detail.status}-${load.detail.user_color}`}
      detail={load.detail}
      deps={deps}
      fresh={fresh}
      initialTab={initialTab}
      initialMoment={initialMoment}
      onTabChange={showTab}
      onLoggedOut={onLoggedOut}
      onAnalyzed={reload}
      autoResume={autoResume}
      onColorChanged={(changed) => {
        setAutoResume(changed.status === 'scanned')
        setLoad({ kind: 'ready', detail: changed })
      }}
      onDeleted={() => void goTo('/games')}
    />
  )
}

interface AnalysisBoardProps {
  detail: GameDetail
  deps: PipelineDeps
  fresh: AnalysisRun | null
  onLoggedOut: () => void
  onAnalyzed: () => void
  autoResume: boolean
  initialTab: Tab
  initialMoment: number | null
  onTabChange: (tab: Tab) => void
  onColorChanged: (detail: GameDetail) => void
  onDeleted: () => void
}

type Tab = 'coach' | 'moments'

function AnalysisBoard({
  detail, deps, fresh, onLoggedOut, onAnalyzed, autoResume, onColorChanged, onDeleted,
  initialTab, initialMoment, onTabChange,
}: AnalysisBoardProps) {
  const [tree, setTree] = useState<GameTree>(() => initialTree(detail))
  // The player's variations save themselves (SPEC_V3 §5.1); every change to the tree goes
  // through changeTree.
  const saver = useVariationSaver(deps.api, detail.id, detail.variations, onLoggedOut)
  // The coach's arrows and highlights (SPEC_V3 §6.3), per board position.
  const drawings = useCoachDrawings(detail.chat)
  function changeTree(updated: GameTree) {
    setTree(updated)
    saver.schedule(updated)
  }
  // Opening on a finished moment shows its position, as choosing it in the moments list does.
  const [current, setCurrent] = useState(() => {
    const opened = initialTab === 'moments' ? detail.moments.find((m) => m.index === initialMoment) : undefined
    return opened && !isUnsolved(opened) ? mainlineNode(tree, opened.ply - 1) : ROOT
  })

  // Critical moments (SPEC_V2 §8.2). While the one on screen is unsolved, the board shows its
  // position, a move played there is the attempt (not added to the tree), and navigation, the
  // engine and the chat are locked (PLAN_V2 §6 Q3). Leaving the tab pauses the exercise.
  const [tab, setTab] = useState<Tab>(initialTab)
  const [moments, setMoments] = useState<MomentInfo[]>(detail.moments)
  const [momentIndex, setMomentIndex] = useState(
    () =>
      (detail.moments.find((m) => m.index === initialMoment) ?? detail.moments.find(isUnsolved) ?? detail.moments[0])
        ?.index ?? 0,
  )
  const [candidate, setCandidate] = useState<string | null>(null)
  const [searches] = useState(() => new BeforeSearches())
  const moment = tab === 'moments' ? (moments.find((m) => m.index === momentIndex) ?? null) : null
  const momentNodeId = moment ? mainlineNode(tree, moment.ply - 1) : null
  const locked = moment !== null && isUnsolved(moment)

  const node = tree.nodes[current]
  // Stored engine lines by position; a finished moment adds its position's lines (SPEC_V3 §7.1).
  const [engineResults, setEngineResults] = useState(detail.engine_results)
  const stored = useMemo(() => storedByPosition(engineResults), [engineResults])

  const [flipped, setFlipped] = useState(false)
  const orientation: 'white' | 'black' = flipped ? (detail.user_color === 'white' ? 'black' : 'white') : detail.user_color
  // The live engine starts as the player's setting until they flip it here (SPEC_V3 §4.3).
  const { settings } = useSettings()
  const [engineChoice, setEngineOn] = useState<boolean | null>(null)
  const engineOn = engineChoice ?? settings.engine_panel
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

  const momentDeps: MomentDeps = {
    api: deps.api,
    async analyzeDeep(fen) {
      const { engine: handle, config } = await loadEngine()
      return handle.analyze({ fen, ply: null }, 'deep', config.deep)
    },
  }

  // Line walkthroughs (SPEC_V3 §7): the board steps through the line; the tree is left alone.
  const walker = useWalkthrough(deps.api, loadEngine, detail.id, onLoggedOut)
  const walking = walker.walk !== null

  const navigate = useCallback((id: string) => {
    if (!locked) setCurrent(id)
  }, [locked])
  const back = useCallback(() => navigate(previous(tree, current)), [navigate, tree, current])
  const forward = useCallback(() => navigate(next(tree, current)), [navigate, tree, current])
  // Explain is triggered inside the chat panel, which registers it here.
  const explainAction = useRef<(() => void) | null>(null)
  const registerExplain = useCallback((explain: (() => void) | null) => {
    explainAction.current = explain
  }, [])
  useShortcuts({
    prev: walking ? walker.prev : back,
    next: walking ? walker.next : forward,
    start: walking ? () => walker.go(0) : () => navigate(ROOT),
    end: walking ? () => walker.go(Number.MAX_SAFE_INTEGER) : () => navigate(endOfLine(tree, current)),
    escape: walking ? walker.close : null,
    walk: !walking && !locked && topLine().length > 0 ? () => walkFrom(current, topLine()) : null,
    flip: () => setFlipped((value) => !value),
    // E and X wait while a moment is unsolved (SPEC_V3 §4.4).
    engine: locked ? null : () => setEngineOn(!engineOn),
    explain: locked || tab !== 'coach' ? null : () => explainAction.current?.(),
    nextMoment: moments.length > 0 ? goToNextMoment : null,
  })

  /** The engine's top line from the board's position: the live one, else the stored one. */
  function topLine(): readonly string[] {
    if (engineOn && live?.fen === node.fen) return live.line.uci
    return stored.get(positionKey(node.fen))?.lines[0]?.moves_uci ?? []
  }
  function walkFrom(startId: string, line: readonly string[]) {
    if (!locked && line.length > 0) walker.open(startId, line.slice(0, WALK_MAX_PLIES))
  }
  function walkVariation(startId: string) {
    walkFrom(tree.nodes[startId].parent ?? ROOT, variationMoves(tree, startId, WALK_MAX_PLIES))
  }
  function saveWalk() {
    const opened = walker.walk
    if (!opened) return
    changeTree(withLine(tree, [...pathTo(opened.startId), ...opened.line]))
    walker.markSaved()
  }

  /** N: the next unfinished critical moment after the one shown (or the first). */
  function goToNextMoment() {
    const after = moments.filter((m) => m.index > momentIndex)
    const target = after.find(isUnsolved) ?? moments.find(isUnsolved) ?? after[0] ?? moments[0]
    if (tab !== 'moments') openTab('moments')
    showMoment(target.index)
  }

  function showMoment(index: number) {
    setMomentIndex(index)
    setCandidate(null)
    const shown = moments.find((m) => m.index === index)
    if (shown && !isUnsolved(shown)) setCurrent(mainlineNode(tree, shown.ply - 1))
  }

  function openTab(next: Tab) {
    setTab(next)
    onTabChange(next)
    setCandidate(null)
    const shown = moments.find((m) => m.index === momentIndex)
    if (next === 'moments' && shown && !isUnsolved(shown)) setCurrent(mainlineNode(tree, shown.ply - 1))
  }

  /** The server's record after a step; a moment that just finished puts its lines on the board. */
  function momentsUpdated(fresh: MomentInfo[], results?: GameDetail['engine_results']) {
    if (results) setEngineResults(results)
    const finished = fresh.filter((m) => !isUnsolved(m) && moments.some((old) => old.index === m.index && isUnsolved(old)))
    setMoments(fresh)
    if (finished.length === 0) return
    const updated = finished.reduce(withMomentLines, tree)
    changeTree(updated)
    setCurrent(mainlineNode(updated, finished[0].ply - 1))
  }

  function play(move: BoardMove) {
    if (moment && locked) {
      if (moment.state === 'intro' || moment.state === 'attempt') setCandidate(toUci(move))
      return
    }
    const result = addMove(tree, current, move)
    if (!result) return // chessground only offers legal moves; nothing to do otherwise
    if (result.tree !== tree) changeTree(result.tree)
    setCurrent(result.nodeId)
  }

  function deleteLine(startId: string) {
    changeTree(deleteVariation(tree, startId))
    if (isWithin(current, startId)) setCurrent(tree.nodes[startId].parent ?? ROOT)
  }

  const promoteLine = (startId: string) => changeTree(promoteVariation(tree, startId))

  const momentFen = momentNodeId !== null ? tree.nodes[momentNodeId].fen : null
  // A moment's messages are all about its position; the latest one's tags are drawn there.
  const momentDrawings = useMemo(
    () =>
      latestByPath(
        (moment?.messages ?? []).map((m) => ({ role: m.role, path: momentNodeId, annotations: m.annotations })),
      ),
    [moment, momentNodeId],
  )
  // The position the board shows, as a node id (null: a moment attempt not yet in the tree).
  const boardPath = locked ? (candidate ? null : momentNodeId) : current
  const coachShapes = drawings.shown(boardPath, tab === 'moments' ? momentDrawings : undefined)

  function showChatTag(path: string, annotation: Annotation | null, how: 'hover' | 'click') {
    if (how === 'click' && path !== current && tree.nodes[path] !== undefined) navigate(path)
    drawings.focus(path, annotation)
  }
  function showMomentTag(annotation: Annotation | null) {
    if (momentNodeId !== null) drawings.focus(momentNodeId, annotation)
  }
  const view = walker.view // while walking, the board shows the step instead
  const gameFen = locked && momentFen ? ((candidate && fenAfter(momentFen, candidate)) ?? momentFen) : node.fen
  const boardFen = view?.fen ?? gameFen
  const gameLastMove = locked && momentNodeId !== null ? (candidate ?? tree.nodes[momentNodeId].uci) : node.uci
  const boardLastMove = view ? (view.lastMove ?? tree.nodes[walker.walk?.startId ?? ROOT]?.uci ?? null) : gameLastMove
  const evaluation = view
    ? { winPct: view.winPct, evalText: view.evalText }
    : locked
    ? candidate || momentNodeId === null
      ? { winPct: null, evalText: null }
      : positionEval(tree.nodes[momentNodeId], detail, stored)
    : engineOn && live?.fen === node.fen
      ? { winPct: live.line.winPct, evalText: live.line.evalText }
      : positionEval(node, detail, stored)
  const points = graphPoints(detail)
  return (
    <section className="analysis" aria-label="Analysis board">
      <GameHeading detail={detail} />
      <GameOptions
        detail={detail}
        api={deps.api}
        onColorChanged={onColorChanged}
        onDeleted={onDeleted}
        onLoggedOut={onLoggedOut}
        beforeExport={saver.flush}
      />
      {detail.status !== 'analyzed' && (
        <ResumeAnalysis
          detail={detail}
          deps={deps}
          autoStart={autoResume}
          onLoggedOut={onLoggedOut}
          onDone={onAnalyzed}
        />
      )}
      <div className="analysis-layout">
        <section className="board-column" aria-label="Board">
          {/* Always shown, so the board never shifts (chessground keeps its screen position). */}
          <BoardTurn
            fen={boardFen}
            moveNumber={view ? Number(boardFen.split(' ')[5]) : locked && moment ? moment.move_number : Math.floor(node.ply / 2) + 1}
          />
          <div className="board-row">
            <EvalBar winPct={evaluation.winPct} evalText={evaluation.evalText} orientation={orientation} />
            <Board
              fen={boardFen}
              orientation={orientation}
              lastMove={boardLastMove}
              movable={!walking && (!locked || (candidate === null && (moment?.state === 'intro' || moment?.state === 'attempt')))}
              onMove={play}
              sound={settings.sounds}
              annotations={view?.annotations ?? coachShapes}
            />
          </div>
          <BoardNav
            disabled={locked}
            onFirst={walking ? () => walker.go(0) : () => navigate(ROOT)}
            onBack={walking ? walker.prev : back}
            onForward={walking ? walker.next : forward}
            onLast={walking ? () => walker.go(Number.MAX_SAFE_INTEGER) : () => navigate(endOfLine(tree, current))}
            onFlip={() => setFlipped((value) => !value)}
          />
          {points.length > 1 && (
            <EvalGraph
              points={points}
              userColor={detail.user_color}
              currentPly={branchPly(tree, node)}
              onSelectPly={(ply) => navigate(mainlineNode(tree, ply))}
            />
          )}
          {locked ? (
            <p className="engine-locked">The engine is off while you work on this moment.</p>
          ) : (
            <EnginePanel
              fen={node.fen}
              enabled={engineOn}
              onToggle={setEngineOn}
              load={loadEngine}
              onBest={setLive}
              onWalk={walking ? undefined : (line) => walkFrom(current, line)}
            />
          )}
          {!locked && !walking && !engineOn && topLine().length > 0 && (
            <Button variant="outline" className="walk-stored" onClick={() => walkFrom(current, topLine())}>
              Walk me through the engine&apos;s line
            </Button>
          )}
          {fresh && <EngineStats run={fresh} />}
        </section>
        <aside className="side-column" aria-label="Coach">
          {walker.walk && (
            <WalkthroughPanel
              walk={walker.walk}
              onStep={walker.go}
              onClose={walker.close}
              onSave={saveWalk}
              onRetry={walker.retry}
            />
          )}
          {/* Hidden, not unmounted, while walking: the chat, its draft and the open panels stay. */}
          <div className="side-coach" hidden={walking}>
            {detail.status === 'analyzed' && moments.length > 0 ? (
              <Tabs
                label="Coaching"
                tabs={[
                  { value: 'coach', label: 'Coach' },
                  { value: 'moments', label: `Critical moments (${moments.filter((m) => !isUnsolved(m)).length}/${moments.length})` },
                ]}
                value={tab}
                onChange={openTab}
              >
                {coachView()}
              </Tabs>
            ) : (
              coachView()
            )}
          </div>
        </aside>
      </div>
    </section>
  )

  function coachView() {
    return (
      <div className="side-stack">
          {detail.status === 'analyzed' && tab === 'moments' && momentFen !== null && (
            <MomentStepper
              gameId={detail.id}
              moments={moments}
              current={momentIndex}
              onSelect={showMoment}
              fen={momentFen}
              candidate={candidate}
              onTakeBack={() => setCandidate(null)}
              deps={momentDeps}
              searches={searches}
              onUpdated={momentsUpdated}
              onLoggedOut={onLoggedOut}
              onBack={() => openTab('coach')}
              onShowTag={showMomentTag}
            />
          )}
          {detail.status === 'analyzed' && tab === 'coach' && (
            <Coach
              detail={detail}
              deps={deps}
              board={node}
              ensureAnalyzed={ensureAnalyzed}
              loadEngine={loadEngine}
              autoSynopsis={fresh !== null}
              spoiler={moments.some(isUnsolved)}
              practice={moments.some(isUnsolved) ? () => openTab('moments') : null}
              unsolved={moments.filter(isUnsolved).length}
              onExplainReady={registerExplain}
              onReply={drawings.record}
              onShowTag={showChatTag}
              moves={
                <MovesPanel count={detail.moves.length}>
                  <MoveList tree={tree} current={current} userColor={detail.user_color} onSelect={navigate} onDelete={deleteLine} onPromote={promoteLine} onWalk={walkVariation} />
                </MovesPanel>
              }
              onLoggedOut={onLoggedOut}
            />
          )}
          {detail.status !== 'analyzed' && (
            <MovesPanel count={detail.moves.length}>
              <MoveList tree={tree} current={current} userColor={detail.user_color} onSelect={navigate} onDelete={deleteLine} onPromote={promoteLine} onWalk={walkVariation} />
            </MovesPanel>
          )}
      </div>
    )
  }
}

/** "White to move · move 3" for the position on the board (Moment.dc.html). */
function BoardTurn({ fen, moveNumber }: { fen: string; moveNumber: number }) {
  const side = fen.split(' ')[1] === 'b' ? 'black' : 'white'
  return (
    <p className="board-turn">
      <ColorSwatch color={side} />
      {side === 'white' ? 'White' : 'Black'} to move · move {moveNumber}
    </p>
  )
}

/** An analysis that didn't finish (the tab was closed): pick it up from where the server says. */
function ResumeAnalysis({ detail, deps, autoStart, onLoggedOut, onDone }: {
  detail: GameDetail
  deps: PipelineDeps
  /** Start without waiting for the button (after a color change). */
  autoStart: boolean
  onLoggedOut: () => void
  onDone: () => void
}) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  async function resume() {
    setError(null)
    setStatus({ phase: 'starting' })
    try {
      const config = await deps.api.engineConfig()
      await resumeGame(deps, detail, config, setStatus)
      onDone()
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
      setStatus(null)
    }
  }

  // StrictMode-safe: start once.
  useEffect(() => {
    if (autoStart && !started.current) {
      started.current = true
      void resume()
    }
  })

  return (
    <div className="resume" role="region" aria-label="Unfinished analysis">
      {status ? (
        <ProgressBar label={statusLabel(status)} {...(status.phase === 'starting' ? { done: 0, total: 1 } : status)} />
      ) : (
        <>
          <p>The engine hasn't finished analyzing this game.</p>
          <Button onClick={() => void resume()}>Resume analysis</Button>
        </>
      )}
      {error && <ErrorState message={`The analysis stopped: ${error}`} onRetry={() => void resume()} />}
    </div>
  )
}

/** The synopsis and the chat, for an analyzed game. */
function Coach({
  detail, deps, board, ensureAnalyzed, loadEngine, autoSynopsis, spoiler, practice, unsolved, moves, onExplainReady,
  onReply, onShowTag, onLoggedOut,
}: {
  detail: GameDetail
  deps: PipelineDeps
  /** The position on the board: chat and Explain are about it (SPEC_V2 §6). */
  board: TreeNode
  ensureAnalyzed: (fen: string, onProgress: (progress: ChatProgress) => void) => Promise<EngineResult | null>
  loadEngine: () => Promise<LiveEngine>
  autoSynopsis: boolean
  /** Unsolved critical moments: the synopsis names their answers, so it starts collapsed (Q16). */
  spoiler: boolean
  /** Open the critical moments ("Practice N critical moments" on the summary card). */
  practice: (() => void) | null
  unsolved: number
  /** The move list, between the summary and the chat (Analysis.dc.html). */
  moves: ReactNode
  /** The chat panel registers Explain here, for the X shortcut. */
  onExplainReady: (explain: (() => void) | null) => void
  /** A coach answer and its board tags, for the board (SPEC_V3 §6.3). */
  onReply: (path: string, annotations: readonly Annotation[]) => void
  onShowTag: ShowChatTag
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

  const practiceButton = practice ? (
    <Button className="synopsis-action" onClick={practice}>
      Practice {unsolved} critical moment{unsolved === 1 ? '' : 's'}
    </Button>
  ) : null

  return (
    <>
      {synopsis && spoiler && synopsis.status === 'done' ? (
        <FeatureCard as="section" className="synopsis" aria-label="Coach's synopsis">
          <CoachSummaryHeading />
          <details className="synopsis-spoiler">
            <summary>Show the summary (spoilers: it names better moves for your critical moments)</summary>
            <div className="synopsis-text">
              <Markdown>{synopsis.text}</Markdown>
            </div>
          </details>
          {practiceButton}
        </FeatureCard>
      ) : synopsis ? (
        <Synopsis state={synopsis} onRetry={() => void write()} action={practiceButton} />
      ) : (
        <FeatureCard as="section" className="synopsis" aria-label="Coach's synopsis">
          <CoachSummaryHeading />
          <p>Your coach can sum up the game's story, its turning point, and the habit to work on.</p>
          <Button className="synopsis-action" onClick={() => void write()}>
            Write a synopsis of this game
          </Button>
        </FeatureCard>
      )}
      {moves}
      <ChatPanel
        onExplainReady={onExplainReady}
        initial={chatMessages(detail.chat)}
        where={positionLabel(board)}
        path={board.id}
        onReply={onReply}
        onShowTag={onShowTag}
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
/** A position's identity for matching stored engine results: FEN without the move counters. */
function positionKey(fen: string): string {
  return fen.split(' ').slice(0, 4).join(' ')
}

function storedByPosition(results: GameDetail['engine_results']): Map<string, GameDetail['engine_results'][number]> {
  return new Map(results.map((result) => [positionKey(result.fen), result]))
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

function toUci(move: BoardMove): string {
  return `${move.from}${move.to}${move.promotion ?? ''}`
}

/** The game, then the saved variations; before the first save, finished moments' lines. */
function initialTree(detail: GameDetail): GameTree {
  const game = fromMoves(detail.moves, detail.final_fen)
  if (detail.variations) return withVariations(game, detail.variations)
  return detail.moments.filter((m) => !isUnsolved(m)).reduce(withMomentLines, game)
}

/** A finished moment's tries and the engine's move, as variations from its position. */
function withMomentLines(tree: GameTree, moment: MomentInfo): GameTree {
  const from = mainlineNode(tree, moment.ply - 1)
  const moves = [...moment.attempts.map((a) => a.uci), ...(moment.best_uci ? [moment.best_uci] : [])]
  return moves.reduce((acc, uci) => addMove(acc, from, fromUci(uci))?.tree ?? acc, tree)
}
