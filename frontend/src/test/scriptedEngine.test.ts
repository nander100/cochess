import { Chess } from 'chess.js'
import { describe, expect, it } from 'vitest'
import { StockfishEngine } from '../engine/StockfishEngine'
import { analyse, openTransport } from './scriptedEngine'

const START = new Chess().fen()

function after(...san: string[]): string {
  const board = new Chess()
  san.forEach((move) => board.move(move))
  return board.fen()
}

describe('the scripted end-to-end engine', () => {
  it('takes a hung piece and scores it from the side to move', () => {
    // 3. Ng5?? leaves the knight to the queen on d8.
    const [best] = analyse(after('e4', 'e5', 'Nf3', 'Nc6', 'Ng5'), 1)

    expect(best.pv[0]).toBe('d8g5')
    expect(best.score).toBe('cp 300')
  })

  it('finds mate in one', () => {
    const [best] = analyse(after('f3', 'e5', 'g4'), 1)

    expect(best).toEqual({ score: 'mate 1', pv: ['d8h4'] })
  })

  it('gives each line as legal moves, the same every time', () => {
    const lines = analyse(START, 3)

    expect(lines).toHaveLength(3)
    for (const { pv } of lines) {
      const board = new Chess()
      pv.forEach((uci) => board.move({ from: uci.slice(0, 2), to: uci.slice(2, 4) }))
    }
    expect(analyse(START, 3)).toEqual(lines)
  })

  it('works behind the real engine wrapper', async () => {
    const opened = openTransport('stockfish-19-lite')
    const engine = await StockfishEngine.connect(opened.transport, 'stockfish-19-lite', 1, 16)
    const tier = { multipv: 2, min_time_ms: 10, min_depth: 18, hard_cap_ms: 500, max_line_plies: 10 }

    const result = await engine.analyze({ fen: START, ply: 0 }, 'verify', tier)

    expect(result.depth).toBeGreaterThanOrEqual(18)
    expect(result.lines.map((line) => line.rank)).toEqual([1, 2])
  })
})
