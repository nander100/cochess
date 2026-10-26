import { useEffect, useState } from 'react'
import {
  type AnalysisRun,
  type AnalysisStatus,
  type PipelineDeps,
  runAnalysis,
  statusLabel,
} from './analysis/pipeline'
import { type ChatDeps, askCoach } from './analysis/chat'
import { clearAccessCode, isAccessDenied, readAccessCode, saveAccessCode } from './api/access'
import { createApiClient } from './api/client'
import type { CreateGameRequest, EngineConfig } from './api/types'
import { AccessGate } from './components/AccessGate'
import { ChatPanel } from './components/ChatPanel'
import { EngineStats } from './components/EngineStats'
import { GameInput } from './components/GameInput'
import { ProgressBar } from './components/ProgressBar'
import { Synopsis, type SynopsisState } from './components/Synopsis'
import { analyzeAll } from './engine/runner'
import { type EngineHandle, StockfishEngine } from './engine/StockfishEngine'

type View =
  | { kind: 'idle' }
  | { kind: 'running'; status: AnalysisStatus }
  | { kind: 'done'; run: AnalysisRun }
  | { kind: 'error'; message: string }

/** Real dependencies. The engine loads once and is reused for every game in this tab. */
function defaultDeps(): PipelineDeps {
  let engine: Promise<EngineHandle> | null = null
  return {
    api: createApiClient(undefined, readAccessCode),
    getEngine(config: EngineConfig) {
      engine ??= StockfishEngine.create(config).catch((error: unknown) => {
        engine = null // let the next attempt retry
        throw error
      })
      return engine
    },
  }
}

interface AppProps {
  deps?: PipelineDeps
}

export default function App({ deps }: AppProps) {
  const [pipeline] = useState(() => deps ?? defaultDeps())
  const [view, setView] = useState<View>({ kind: 'idle' })
  const [synopsis, setSynopsis] = useState<SynopsisState | null>(null)
  const [access, setAccess] = useState<'checking' | 'locked' | 'open'>('checking')
  const [accessError, setAccessError] = useState<string | null>(null)

  // One cheap gated request tells us whether this browser session needs the access code.
  useEffect(() => {
    pipeline.api.engineConfig().then(
      () => setAccess('open'),
      (error: unknown) => setAccess(isAccessDenied(error) ? 'locked' : 'open'),
    )
  }, [pipeline])

  async function unlock(code: string) {
    saveAccessCode(code)
    setAccess('checking')
    setAccessError(null)
    try {
      await pipeline.api.engineConfig()
      setAccess('open')
    } catch (error) {
      if (isAccessDenied(error)) clearAccessCode()
      setAccess('locked')
      setAccessError(isAccessDenied(error) ? "That access code didn't work." : errorText(error))
    }
  }

  /** A 401 mid-session (the code was changed on the server): back to the gate. */
  function lockIfDenied(error: unknown): boolean {
    if (!isAccessDenied(error)) return false
    clearAccessCode()
    setAccess('locked')
    setAccessError('Please enter the access code again.')
    return true
  }

  async function analyze(request: CreateGameRequest) {
    setView({ kind: 'running', status: { phase: 'starting' } })
    setSynopsis(null)
    try {
      const run = await runAnalysis(pipeline, request, (status) =>
        setView({ kind: 'running', status }),
      )
      setView({ kind: 'done', run })
      if (run.outcome.summary_ready) void coach(run.game.game_id)
    } catch (error) {
      if (lockIfDenied(error)) setView({ kind: 'idle' })
      else setView({ kind: 'error', message: errorText(error) })
    }
  }

  /** Chat deep-dives run on the same in-browser engine, with the deep tier's settings. */
  function chatDeps(run: AnalysisRun): ChatDeps {
    return {
      api: pipeline.api,
      async analyzeDeep(positions) {
        const engine = await pipeline.getEngine(run.config)
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
      await pipeline.api.streamSynopsis(gameId, (event) => {
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
      if (!lockIfDenied(error)) setSynopsis({ status: 'error', text, error: errorText(error) })
    }
  }

  if (access !== 'open') {
    return (
      <main>
        <Header />
        {access === 'locked' ? (
          <AccessGate error={accessError} onUnlock={(code) => void unlock(code)} />
        ) : (
          <p className="coach-writing">Connecting…</p>
        )}
      </main>
    )
  }

  return (
    <main>
      <Header />

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
    </main>
  )
}

function Header() {
  return (
    <header>
      <h1>CoChess</h1>
      <p className="tagline">Paste a game. The engine finds what happened; your coach explains it.</p>
    </header>
  )
}

/** Accuracy and error counts from the backend's game summary (the coach's synopsis is M4). */
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

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

function progressOf(status: AnalysisStatus): { done: number; total: number } {
  return status.phase === 'starting' ? { done: 0, total: 1 } : status
}
