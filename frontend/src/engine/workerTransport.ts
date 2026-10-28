import type { EngineBuild } from './StockfishEngine'
import type { EngineTransport } from './search'

/** A started engine: its UCI transport, how to stop it, and a promise that rejects if it can't
 * load. */
export interface OpenedEngine {
  transport: EngineTransport
  terminate: () => void
  loadFailed: Promise<never>
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

/** Stockfish in a Web Worker, from the builds `npm install` copies into public/engine/. */
export function openTransport(build: EngineBuild): OpenedEngine {
  const worker = new Worker(`/engine/${build}.js`)
  const loadFailed = new Promise<never>((_, reject) => {
    worker.onerror = () => reject(new Error("The chess engine couldn't be loaded."))
  })
  return { transport: new WorkerTransport(worker), terminate: () => worker.terminate(), loadFailed }
}
