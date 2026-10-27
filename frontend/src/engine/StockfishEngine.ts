import type { EngineConfig, EngineResult, Tier, TierConfig } from '../api/types'
import { type EngineTransport, type SearchOutcome, search, toEngineResult } from './search'
import type { InfoLine } from './uci'

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
  /**
   * The live panel's search (SPEC_V2 §5.5): runs until `signal` aborts or the tier's cap,
   * reporting lines as they deepen. Any other search or newGame() stops it first.
   */
  analyzeLive(
    fen: string,
    tier: TierConfig,
    onUpdate: (lines: InfoLine[], depth: number) => void,
    signal: AbortSignal,
  ): Promise<SearchOutcome>
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
  // The running live search, which gives way to any other work.
  private live: AbortController | null = null

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
    if (typeof Worker === 'undefined' || typeof WebAssembly === 'undefined') {
      throw new Error(
        "Your browser can't run the chess engine. Please use a recent version of Chrome, " +
          'Firefox, Edge or Safari.',
      )
    }
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
    this.live?.abort()
    return this.enqueue(async () => {
      const outcome = await search(this.transport, item.fen, tier)
      return toEngineResult(item.fen, item.ply, tierName, tier, outcome)
    })
  }

  /** Clear the engine's hash between games. */
  analyzeLive(
    fen: string,
    tier: TierConfig,
    onUpdate: (lines: InfoLine[], depth: number) => void,
    signal: AbortSignal,
  ): Promise<SearchOutcome> {
    this.live?.abort() // one live search at a time
    const controller = new AbortController()
    this.live = controller
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', () => controller.abort(), { once: true })
    return this.enqueue(() =>
      search(this.transport, fen, tier, { signal: controller.signal, onInfo: onUpdate }),
    ).finally(() => {
      if (this.live === controller) this.live = null
    })
  }

  newGame(): Promise<void> {
    this.live?.abort()
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
