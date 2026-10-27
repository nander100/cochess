import { useEffect, useId, useRef, useState } from 'react'
import type { EngineConfig } from '../api/types'
import { type LiveLine, isGameOver, toLiveLines } from '../engine/live'
import type { EngineHandle } from '../engine/StockfishEngine'

export interface LiveEngine {
  engine: EngineHandle
  config: EngineConfig
}

interface EnginePanelProps {
  fen: string
  enabled: boolean
  onToggle: (enabled: boolean) => void
  /** Loads the browser engine (once per tab) and the tier settings. */
  load: () => Promise<LiveEngine>
  /** The best line for `fen` as it deepens (for the eval bar), or null when there's none. */
  onBest: (best: { fen: string; line: LiveLine } | null) => void
}

/** A search of one position; anything shown for another position is derived as "loading". */
type Search =
  | { fen: string; kind: 'running' | 'stopped'; engine: EngineHandle; config: EngineConfig; lines: LiveLine[]; depth: number }
  | { fen: string; kind: 'error'; message: string }

type Status = { kind: 'idle' | 'loading' | 'game-over' } | Search

/**
 * The live engine (SPEC_V2 §5.5): off by default; when on, searches the position on the board
 * (top 3 lines), restarting when the position changes and stopping after the tier's cap.
 */
export function EnginePanel({ fen, enabled, onToggle, load, onBest }: EnginePanelProps) {
  const id = useId()
  const [search, setSearch] = useState<Search | null>(null)
  const report = useRef(onBest)
  useEffect(() => {
    report.current = onBest
  }, [onBest])

  useEffect(() => {
    if (!enabled || isGameOver(fen)) return
    const controller = new AbortController()
    const live = controller.signal
    load()
      .then(async ({ engine, config }) => {
        if (live.aborted) return
        setSearch({ fen, kind: 'running', engine, config, lines: [], depth: 0 })
        await engine.analyzeLive(
          fen,
          config.live,
          (infoLines, depth) => {
            if (live.aborted) return
            const lines = toLiveLines(fen, infoLines, config.live.max_line_plies)
            setSearch({ fen, kind: 'running', engine, config, lines, depth })
            if (lines[0]) report.current({ fen, line: lines[0] })
          },
          live,
        )
        if (!live.aborted) setSearch((s) => (s?.fen === fen && s.kind === 'running' ? { ...s, kind: 'stopped' } : s))
      })
      .catch((error: unknown) => {
        if (!live.aborted) {
          setSearch({ fen, kind: 'error', message: error instanceof Error ? error.message : 'The engine failed.' })
        }
      })
    return () => controller.abort()
  }, [enabled, fen, load])

  const status: Status = !enabled
    ? { kind: 'idle' }
    : isGameOver(fen)
      ? { kind: 'game-over' }
      : search?.fen === fen
        ? search
        : { kind: 'loading' }
  const lines = status.kind === 'running' || status.kind === 'stopped' ? status.lines : []
  return (
    <section className="engine-panel" aria-label="Live engine">
      <label htmlFor={`${id}-toggle`} className="engine-toggle">
        <input
          id={`${id}-toggle`}
          type="checkbox"
          checked={enabled}
          onChange={(event) => onToggle(event.target.checked)}
        />
        Engine
      </label>
      <EngineStatus status={status} />
      {lines.length > 0 && (
        <ol className="engine-lines" aria-label="Engine lines">
          {lines.map((line) => (
            <li key={line.rank}>
              <span className="engine-eval">{line.evalText}</span> {line.text}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function EngineStatus({ status }: { status: Status }) {
  switch (status.kind) {
    case 'idle':
      return null
    case 'loading':
      return <p className="engine-status">Loading the engine…</p>
    case 'game-over':
      return <p className="engine-status">The game is over in this position.</p>
    case 'error':
      return (
        <p className="run-error" role="alert">
          {status.message}
        </p>
      )
    case 'running':
    case 'stopped': {
      const name = status.engine.build === 'stockfish-19-lite' ? 'Stockfish 19 lite' : 'Stockfish 19 lite (single-threaded)'
      const cap = Math.round(status.config.live.hard_cap_ms / 1000)
      return (
        <p className="engine-status" role="status">
          {name} · {status.engine.threads} thread(s) · depth {status.depth}
          {status.kind === 'stopped' && ` · stopped after ${cap} s`}
        </p>
      )
    }
  }
}
