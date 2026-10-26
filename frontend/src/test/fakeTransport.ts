import type { EngineTransport } from '../engine/search'

/** A scripted stand-in for the Stockfish worker. `respond` reacts to each command sent. */
export class FakeTransport implements EngineTransport {
  readonly sent: string[] = []
  respond: (command: string, transport: FakeTransport) => void = () => {}
  private readonly listeners = new Set<(line: string) => void>()

  send(command: string): void {
    this.sent.push(command)
    this.respond(command, this)
  }

  onLine(listener: (line: string) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  emit(line: string): void {
    ;[...this.listeners].forEach((listener) => listener(line))
  }

  get listenerCount(): number {
    return this.listeners.size
  }
}

export function info(depth: number, score: string, pv: string, multipv = 1): string {
  return `info depth ${depth} seldepth ${depth + 4} multipv ${multipv} score ${score} nodes 1000 nps 50000 time 20 pv ${pv}`
}
