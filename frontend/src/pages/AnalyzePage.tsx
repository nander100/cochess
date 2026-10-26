import { useState } from 'react'
import {
  type AnalysisRun,
  type AnalysisStatus,
  type PipelineDeps,
  runAnalysis,
  statusLabel,
} from '../analysis/pipeline'
import { type ChatDeps, askCoach } from '../analysis/chat'
import { isLoggedOut } from '../api/client'
import type { CreateGameRequest } from '../api/types'
import { ChatPanel } from '../components/ChatPanel'
import { EngineStats } from '../components/EngineStats'
import { GameInput } from '../components/GameInput'
import { ProgressBar } from '../components/ProgressBar'
import { Synopsis, type SynopsisState } from '../components/Synopsis'
import { analyzeAll } from '../engine/runner'
import { errorText } from './util'

type View =
  | { kind: 'idle' }
  | { kind: 'running'; status: AnalysisStatus }
  | { kind: 'done'; run: AnalysisRun }
  | { kind: 'error'; message: string }

interface AnalyzePageProps {
  deps: PipelineDeps
  /** The server answered 401: the session ended. */
  onLoggedOut: () => void
}

/** Paste a game, run the engine, read the synopsis, ask the coach (the v1 flow). */
export function AnalyzePage({ deps, onLoggedOut }: AnalyzePageProps) {
  const [view, setView] = useState<View>({ kind: 'idle' })
  const [synopsis, setSynopsis] = useState<SynopsisState | null>(null)

  async function analyze(request: CreateGameRequest) {
    setView({ kind: 'running', status: { phase: 'starting' } })
    setSynopsis(null)
    try {
      const run = await runAnalysis(deps, request, (status) => setView({ kind: 'running', status }))
      setView({ kind: 'done', run })
      if (run.outcome.summary_ready) void coach(run.game.game_id)
    } catch (error) {
      if (isLoggedOut(error)) onLoggedOut()
      else setView({ kind: 'error', message: errorText(error) })
    }
  }

  /** Chat deep-dives run on the same in-browser engine, with the deep tier's settings. */
  function chatDeps(run: AnalysisRun): ChatDeps {
    return {
      api: deps.api,
      async analyzeDeep(positions) {
        const engine = await deps.getEngine(run.config)
        const items = positions.map((p) => ({ fen: p.fen, ply: null }))
        return analyzeAll(engine, items, 'deep', run.config.deep)
      },
    }
  }

  async function coach(gameId: string) {
    setSynopsis({ status: 'writing', text: '', error: null })
    let text = ''
    let finished = false
    try {
      await deps.api.streamSynopsis(gameId, (event) => {
        if (event.type === 'text') {
          text += event.text
          setSynopsis({ status: 'writing', text, error: null })
        } else if (event.type === 'done' || event.type === 'error') {
          finished = true
          const error = event.type === 'error' ? event.message : null
          setSynopsis({ status: error ? 'error' : 'done', text, error })
        }
      })
      if (!finished) {
        setSynopsis({ status: 'error', text, error: 'The connection to the coach was lost.' })
      }
    } catch (error) {
      if (isLoggedOut(error)) onLoggedOut()
      else setSynopsis({ status: 'error', text, error: errorText(error) })
    }
  }

  return (
    <>
      <GameInput disabled={view.kind === 'running'} onSubmit={(request) => void analyze(request)} />

      {view.kind === 'running' && (
        <ProgressBar label={statusLabel(view.status)} {...progressOf(view.status)} />
      )}
      {view.kind === 'error' && (
        <p className="run-error" role="alert">
          {view.message}
        </p>
      )}
      {view.kind === 'done' && (
        <section className="result" aria-label="Analysis">
          <p>Analysis complete.</p>
          <ResultHeadline run={view.run} />
          <div className="coach-columns">
            {synopsis && (
              <Synopsis state={synopsis} onRetry={() => void coach(view.run.game.game_id)} />
            )}
            {synopsis && synopsis.status !== 'writing' && (
              <ChatPanel
                key={view.run.game.game_id}
                ask={(message, onProgress) =>
                  askCoach(chatDeps(view.run), view.run.game.game_id, message, onProgress)
                }
              />
            )}
          </div>
          <EngineStats run={view.run} />
        </section>
      )}
    </>
  )
}

/** Accuracy and error counts from the backend's game summary. */
function ResultHeadline({ run }: { run: AnalysisRun }) {
  const { accuracy, counts } = run.outcome
  if (!accuracy || !counts) return null
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  return (
    <p className="headline">
      Your accuracy: <strong>{accuracy.user ?? '—'}%</strong> (opponent{' '}
      {accuracy.opponent ?? '—'}%) · {count(counts.inaccuracies, 'inaccuracy', 'inaccuracies')},{' '}
      {count(counts.mistakes, 'mistake', 'mistakes')}, {count(counts.blunders, 'blunder', 'blunders')}
    </p>
  )
}

function progressOf(status: AnalysisStatus): { done: number; total: number } {
  return status.phase === 'starting' ? { done: 0, total: 1 } : status
}
