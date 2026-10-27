import type { EngineResult, Tier, TierConfig } from '../api/types'
import { toWhitePov } from './score'
import { type InfoLine, parseInfoLine } from './uci'

/** How long to wait for `bestmove` after sending `stop` before giving up on the engine. */
export const STOP_GRACE_MS = 3000

export interface EngineTransport {
  send(command: string): void
  /** Subscribe to engine output lines. Returns an unsubscribe function. */
  onLine(listener: (line: string) => void): () => void
}

export interface SearchOutcome {
  depth: number
  timeMs: number
  lines: InfoLine[] // ordered by multipv
}

export interface SearchOptions {
  now?: () => number
  /** Stop early (sends `stop`); the search resolves with the lines found so far. */
  signal?: AbortSignal
  /** Called on every line update with all current lines (ordered by multipv) and the depth. */
  onInfo?: (lines: InfoLine[], depth: number) => void
}

/**
 * Run one search with "minimum time, minimum depth, hard cap" control (SPEC §5.2):
 * `go infinite`, then `stop` once BOTH the minimum time and minimum depth are reached, or when
 * the hard cap is hit, whichever comes first. The caller must not start another search on the
 * same transport until this one settles.
 */
export function search(
  transport: EngineTransport,
  fen: string,
  tier: TierConfig,
  { now = () => performance.now(), signal, onInfo }: SearchOptions = {},
): Promise<SearchOutcome> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      resolve({ depth: 0, timeMs: 0, lines: [] }) // cancelled before it started: nothing sent
      return
    }
    const lines = new Map<number, InfoLine>()
    const timers: ReturnType<typeof setTimeout>[] = []
    const start = now()
    let depth = 0
    let stopSent = false

    const settle = () => {
      unsubscribe()
      timers.forEach(clearTimeout)
      signal?.removeEventListener('abort', stopNow)
    }

    const ordered = () => [...lines.entries()].sort(([a], [b]) => a - b).map(([, info]) => info)

    function stopNow() {
      if (stopSent) return
      stopSent = true
      transport.send('stop')
      timers.push(
        setTimeout(() => {
          settle()
          reject(new Error('The engine stopped responding.'))
        }, STOP_GRACE_MS),
      )
    }

    const maybeStop = () => {
      if (stopSent) return
      const elapsed = now() - start
      const satisfied = elapsed >= tier.min_time_ms && depth >= tier.min_depth
      if (satisfied || elapsed >= tier.hard_cap_ms) stopNow()
    }

    const unsubscribe = transport.onLine((line) => {
      if (line.startsWith('bestmove')) {
        settle()
        resolve({ depth, timeMs: Math.round(now() - start), lines: ordered() })
        return
      }
      const info = parseInfoLine(line)
      if (info === null || info.multipv > tier.multipv) return
      lines.set(info.multipv, info)
      // Iteration depth is complete once the main line (multipv 1) reports it.
      if (info.multipv === 1) depth = Math.max(depth, info.depth)
      onInfo?.(ordered(), depth)
      maybeStop()
    })

    signal?.addEventListener('abort', stopNow, { once: true })
    timers.push(setTimeout(maybeStop, tier.min_time_ms), setTimeout(maybeStop, tier.hard_cap_ms))
    transport.send(`setoption name MultiPV value ${tier.multipv}`)
    transport.send(`position fen ${fen}`)
    transport.send('go infinite')
  })
}

/** Convert a search outcome into the SPEC §5.4 result posted to the backend. */
export function toEngineResult(
  fen: string,
  ply: number | null,
  tierName: Tier,
  tier: TierConfig,
  outcome: SearchOutcome,
): EngineResult {
  return {
    ply,
    fen,
    tier: tierName,
    depth: outcome.depth,
    time_ms: outcome.timeMs,
    lines: outcome.lines.map((info, index) => ({
      rank: index + 1,
      ...toWhitePov(fen, info.score),
      moves_uci: info.pv.slice(0, tier.max_line_plies),
    })),
  }
}
