import { Chess, type Move } from 'chess.js'
import type { EngineBuild } from '../engine/StockfishEngine'
import type { EngineTransport } from '../engine/search'
import type { OpenedEngine } from '../engine/workerTransport'

/**
 * A scripted engine for end-to-end tests (vite.config.ts aliases `@engine-transport` here when
 * E2E_FAKE_ENGINE=1). It speaks the UCI subset CoChess uses and plays real chess with chess.js,
 * so every line it reports is legal and the backend accepts it. Its "evaluation" is material
 * after a two-ply look-ahead: hanging a piece is a real drop, which makes a critical moment.
 * Deterministic: the same position always gets the same lines.
 */

const VALUE: Record<string, number> = { p: 100, n: 300, b: 300, r: 500, q: 900, k: 0 }
const MATE = 100_000
const REPORTED_DEPTH = 30 // above every tier's minimum, so searches stop at their minimum time
const LINE_PLIES = 4

interface ScriptedLine {
  score: string // UCI score, from the side to move: "cp 300" or "mate 1"
  pv: string[]
}

class ScriptedTransport implements EngineTransport {
  private readonly listeners = new Set<(line: string) => void>()
  private fen = new Chess().fen()
  private multipv = 1
  private best: string | null = null

  send(command: string): void {
    const [verb, ...rest] = command.trim().split(/\s+/)
    if (verb === 'uci') this.emitSoon('id name CoChess scripted engine', 'uciok')
    else if (verb === 'isready') this.emitSoon('readyok')
    else if (verb === 'setoption' && rest[1] === 'MultiPV') this.multipv = Number(rest[3]) || 1
    else if (verb === 'position') this.position(rest)
    else if (verb === 'go') this.go()
    else if (verb === 'stop') this.emitSoon(`bestmove ${this.best ?? '(none)'}`)
  }

  onLine(listener: (line: string) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private position(args: string[]): void {
    const movesAt = args.indexOf('moves')
    const fenTokens = args[0] === 'fen' ? args.slice(1, movesAt < 0 ? undefined : movesAt) : []
    const board = new Chess(fenTokens.length ? fenTokens.join(' ') : undefined)
    for (const uci of movesAt < 0 ? [] : args.slice(movesAt + 1)) board.move(uciMove(uci))
    this.fen = board.fen()
  }

  /** Report every line at once; the search then "runs" until the caller sends stop. */
  private go(): void {
    const lines = analyse(this.fen, this.multipv)
    this.best = lines[0]?.pv[0] ?? null
    this.emitSoon(
      ...lines.map(
        (line, i) =>
          `info depth ${REPORTED_DEPTH} seldepth ${REPORTED_DEPTH} multipv ${i + 1} score ${line.score} ` +
          `nodes 1000 nps 100000 time 10 pv ${line.pv.join(' ')}`,
      ),
    )
  }

  /** After the command returns, like a worker's messages. */
  private emitSoon(...lines: string[]): void {
    setTimeout(() => lines.forEach((line) => [...this.listeners].forEach((listener) => listener(line))), 0)
  }
}

/** The best `count` moves by two-ply material, each with a short greedy line. */
export function analyse(fen: string, count: number): ScriptedLine[] {
  const board = new Chess(fen)
  return ranked(board)
    .slice(0, count)
    .map(({ move, value }) => ({
      score: value >= MATE ? 'mate 1' : `cp ${value}`,
      pv: line(board, move),
    }))
}

function ranked(board: Chess): { move: Move; value: number }[] {
  return board
    .moves({ verbose: true })
    .map((move) => ({ move, value: valueAfter(board, move) }))
    .sort((a, b) => b.value - a.value || a.move.lan.localeCompare(b.move.lan))
}

/** Material for the side to move after `move` and the opponent's best reply. Mate is read from
 * the SAN ("#"), which chess.js already worked out, so no extra move generation is needed. */
function valueAfter(board: Chess, move: Move): number {
  if (move.san.endsWith('#')) return MATE
  const side = board.turn()
  board.move(move)
  const replies = board.moves({ verbose: true })
  let value = 0 // stalemate
  if (replies.length > 0) {
    value = Math.min(
      ...replies.map((reply) => {
        if (reply.san.endsWith('#')) return -MATE
        board.move(reply)
        const after = material(board, side)
        board.undo()
        return after
      }),
    )
  }
  board.undo()
  return value
}

function material(board: Chess, side: 'w' | 'b'): number {
  let total = 0
  for (const row of board.board()) {
    for (const piece of row) {
      if (piece) total += (piece.color === side ? 1 : -1) * VALUE[piece.type]
    }
  }
  return total
}

/** The move, then each side's greedy best (mate, else the biggest capture) for a few plies:
 * legal, and the same every time. */
function line(board: Chess, first: Move): string[] {
  const copy = new Chess(board.fen())
  const pv = [first.lan]
  copy.move(first)
  while (pv.length < LINE_PLIES) {
    const moves = copy.moves({ verbose: true })
    if (moves.length === 0) break
    const next = moves.reduce((best, move) => (greed(move) > greed(best) ? move : best))
    pv.push(next.lan)
    copy.move(next)
  }
  return pv
}

function greed(move: Move): number {
  return move.san.endsWith('#') ? MATE : move.captured ? VALUE[move.captured] : 0
}

function uciMove(uci: string): { from: string; to: string; promotion?: string } {
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), ...(uci.length > 4 ? { promotion: uci[4] } : {}) }
}

export function openTransport(_build: EngineBuild): OpenedEngine {
  return { transport: new ScriptedTransport(), terminate: () => {}, loadFailed: new Promise<never>(() => {}) }
}
