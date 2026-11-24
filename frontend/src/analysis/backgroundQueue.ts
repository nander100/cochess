import { isLoggedOut } from '../api/client'
import type { EngineConfig } from '../api/types'
import { type PipelineDeps, resumeGame } from './pipeline'
import type { QueueProgress } from './queue'

/** Where the waiting game ids are kept between page loads. */
export interface QueueStorage {
  load(): string[]
  save(ids: string[]): void
}

export interface QueueState {
  /** Waiting to be analyzed; while running, the first is the one in progress. */
  pending: readonly string[]
  /** Analyzed in this run, in order. */
  finished: readonly string[]
  /** Couldn't be analyzed in this run (they stay in the player's list to try again). */
  failed: readonly string[]
  running: boolean
  /** The session ended mid-run: what's left waits until the player signs in again. */
  loggedOut: boolean
  progress: QueueProgress | null
}

/** Run a task while holding the tab-wide analysis lock, so only one tab analyzes at a time. */
export type QueueLock = (task: () => Promise<void>) => Promise<void>

/**
 * Imported games analyzed in the background (SPEC_V4 §8.2): the queue lives with the app, not a
 * page, so the player keeps using CoChess while it runs, and its waiting list is stored so a reload
 * carries on. The server keeps each game's progress, so a game left half-done is resumed; a game
 * that fails is set aside and the rest go on; being logged out stops the run and keeps the rest.
 */
export class AnalysisQueue {
  private current: QueueState
  private readonly listeners = new Set<(state: QueueState) => void>()
  private config: EngineConfig | null = null
  private readonly deps: PipelineDeps
  private readonly storage: QueueStorage
  private readonly lock: QueueLock | null

  constructor(deps: PipelineDeps, storage: QueueStorage, lock: QueueLock | null = null) {
    this.deps = deps
    this.storage = storage
    this.lock = lock
    this.current = {
      pending: storage.load(),
      finished: [],
      failed: [],
      running: false,
      loggedOut: false,
      progress: null,
    }
  }

  get state(): QueueState {
    return this.current
  }

  subscribe(listener: (state: QueueState) => void): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  /** Queue games for analysis (each once) and start if idle. */
  add(gameIds: readonly string[]): void {
    const fresh = gameIds.filter((id, i) => !this.current.pending.includes(id) && gameIds.indexOf(id) === i)
    if (fresh.length === 0) return
    const newRun = this.current.running ? {} : { finished: [], failed: [], loggedOut: false }
    this.update({ ...newRun, pending: [...this.current.pending, ...fresh] })
    this.resume()
  }

  /** Carry on with stored games (after a reload, or after signing in again). */
  resume(): void {
    if (this.current.running || this.current.pending.length === 0) return
    void this.run()
  }

  /** Forget the queue (signing out, so the next player in this browser doesn't inherit it). */
  clear(): void {
    this.update({ pending: [], finished: [], failed: [], progress: null })
  }

  private async run(): Promise<void> {
    this.update({ running: true, loggedOut: false })
    const task = () => this.drain()
    try {
      await (this.lock ? this.lock(task) : task())
    } finally {
      this.update({ running: false, progress: null })
    }
  }

  private async drain(): Promise<void> {
    while (this.current.pending.length > 0) {
      const id = this.current.pending[0]
      const game = this.current.finished.length + this.current.failed.length + 1
      const total = game - 1 + this.current.pending.length
      try {
        this.update({ progress: { game, total, status: { phase: 'starting' } } })
        const detail = await this.deps.api.getGame(id)
        if (detail.status !== 'analyzed') {
          this.config ??= await this.deps.api.engineConfig()
          await resumeGame(this.deps, detail, this.config, (status) =>
            this.update({ progress: { game, total, status } }),
          )
        }
        this.settle(id, 'finished')
      } catch (error) {
        if (isLoggedOut(error)) {
          this.update({ loggedOut: true })
          return
        }
        this.settle(id, 'failed')
      }
    }
  }

  private settle(id: string, outcome: 'finished' | 'failed'): void {
    const pending = this.current.pending.filter((waiting) => waiting !== id)
    if (outcome === 'finished') this.update({ pending, finished: [...this.current.finished, id] })
    else this.update({ pending, failed: [...this.current.failed, id] })
  }

  private update(change: Partial<QueueState>): void {
    this.current = { ...this.current, ...change }
    if ('pending' in change) this.storage.save([...this.current.pending])
    for (const listener of this.listeners) listener(this.current)
  }
}

const STORAGE_KEY = 'cochess.analysisQueue'

/** The waiting list in localStorage; anything unreadable counts as empty. */
export function browserStorage(): QueueStorage {
  return {
    load() {
      try {
        const saved: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
        return Array.isArray(saved) ? saved.filter((id): id is string => typeof id === 'string') : []
      } catch {
        return []
      }
    },
    save(ids) {
      if (ids.length === 0) localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
    },
  }
}

/** One analyzing tab at a time, where the browser supports Web Locks; otherwise no lock. */
export function browserLock(): QueueLock | null {
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
  if (!locks) return null
  return (task) => locks.request('cochess-analysis-queue', task)
}
