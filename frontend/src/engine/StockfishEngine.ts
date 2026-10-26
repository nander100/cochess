import type { EngineConfig, EngineResult, Tier, TierConfig } from '../api/types'
import { type EngineTransport, search, toEngineResult } from './search'

export type EngineBuild = 'stockfish-19-lite' | 'stockfish-19-lite-single'

/** The wasm download and compile can take a while on slow connections. */
const LOAD_TIMEOUT_MS = 30_000
const READY_TIMEOUT_MS = 10_000

export interface AnalysisItem {
  fen: string
  ply: number | null
}

export interface Analyzer {
  analyze(item: AnalysisItem, tierName: Tier, tier: TierConfig): Promise<EngineResult>
}

export interface EngineHandle extends Analyzer {
  readonly build: EngineBuild
  readonly threads: number
  newGame(): Promise<void>
}

/** Multi-threaded Stockfish needs SharedArrayBuffer, which needs cross-origin isolation (§4.1). */
export function chooseBuild(crossOriginIsolated: boolean): EngineBuild {
  return crossOriginIsolated ? 'stockfish-19-lite' : 'stockfish-19-lite-single'
}

/** Leave one core for the page; never exceed the configured maximum. */
export function threadCount(
  build: EngineBuild,
  hardwareConcurrency: number,
  maxThreads: number,
): number {
  if (build === 'stockfish-19-lite-single') return 1
  return Math.max(1, Math.min(hardwareConcurrency - 1, maxThreads))
}

export function waitForLine(
  transport: EngineTransport,
  expected: string,
  timeoutMs: number,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      unsubscribe()
      reject(new Error(`The chess engine didn't answer (waiting for "${expected}").`))
    }, timeoutMs)
    const unsubscribe = transport.onLine((line) => {
      if (line.trim() !== expected) return
      clearTimeout(timer)
      unsubscribe()
      resolve()
    })
  })
}

class WorkerTransport implements EngineTransport {
  private readonly listeners = new Set<(line: string) => void>()
  private readonly worker: Worker

  constructor(worker: Worker) {
    this.worker = worker
    worker.onmessage = (event: MessageEvent) => {
      const line = String(event.data)
      this.listeners.forEach((listener) => listener(line))
    }
  }

  send(command: string): void {
    this.worker.postMessage(command)
  }

  onLine(listener: (line: string) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }
}

export class StockfishEngine implements EngineHandle {
  readonly build: EngineBuild
  readonly threads: number
  private readonly transport: EngineTransport
  private readonly worker: Worker | null
  // Searches share one engine, so they run strictly one after another.
  private queue: Promise<unknown> = Promise.resolve()

  private constructor(
    transport: EngineTransport,
    build: EngineBuild,
    threads: number,
    worker: Worker | null,
  ) {
    this.transport = transport
    this.build = build
    this.threads = threads
    this.worker = worker
  }

  /** Start the right Stockfish build in a Web Worker and complete the UCI handshake. */
  static async create(config: EngineConfig): Promise<StockfishEngine> {
    const build = chooseBuild(globalThis.crossOriginIsolated === true)
    const threads = threadCount(build, navigator.hardwareConcurrency || 2, config.max_threads)
    const worker = new Worker(`/engine/${build}.js`)
    const loadFailed = new Promise<never>((_, reject) => {
      worker.onerror = () => reject(new Error("The chess engine couldn't be loaded."))
    })
    loadFailed.catch(() => undefined) // only matters while racing the handshake below
    try {
      const transport = new WorkerTransport(worker)
      const engine = await Promise.race([
        StockfishEngine.connect(transport, build, threads, config.hash_mb, worker),
        loadFailed,
      ])
      console.info(`CoChess engine: ${build}, ${threads} thread(s)`)
      return engine
    } catch (error) {
      worker.terminate()
      throw error
    }
  }

  /** Handshake over any transport (exposed for tests). */
  static async connect(
    transport: EngineTransport,
    build: EngineBuild,
    threads: number,
    hashMb: number,
    worker: Worker | null = null,
  ): Promise<StockfishEngine> {
    const uciOk = waitForLine(transport, 'uciok', LOAD_TIMEOUT_MS)
    transport.send('uci')
    await uciOk
    if (build === 'stockfish-19-lite') transport.send(`setoption name Threads value ${threads}`)
    transport.send(`setoption name Hash value ${hashMb}`)
    const engine = new StockfishEngine(transport, build, threads, worker)
    await engine.ready()
    return engine
  }

  analyze(item: AnalysisItem, tierName: Tier, tier: TierConfig): Promise<EngineResult> {
    return this.enqueue(async () => {
      const outcome = await search(this.transport, item.fen, tier)
      return toEngineResult(item.fen, item.ply, tierName, tier, outcome)
    })
  }

  /** Clear the engine's hash between games. */
  newGame(): Promise<void> {
    return this.enqueue(async () => {
      this.transport.send('ucinewgame')
      await this.ready()
    })
  }

  dispose(): void {
    this.worker?.terminate()
  }

  private ready(): Promise<void> {
    const readyOk = waitForLine(this.transport, 'readyok', READY_TIMEOUT_MS)
    this.transport.send('isready')
    return readyOk
  }

  private enqueue<T>(task: () => Promise<T>): Promise<T> {
    const run = this.queue.then(task, task)
    this.queue = run.catch(() => undefined)
    return run
  }
}
