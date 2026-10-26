import type { CreateGameResponse, EngineResult, TierConfig } from '../api/types'
import { analyzeAll, itemsForFens, moveNumber, scanItems } from './runner'
import type { AnalysisItem, Analyzer } from './StockfishEngine'

const TIER: TierConfig = { multipv: 1, min_time_ms: 1, min_depth: 1, hard_cap_ms: 1, max_line_plies: 1 }

function game(finalIsTerminal: boolean): CreateGameResponse {
  return {
    game_id: 'g1',
    positions: [
      { ply: 1, fen_before: 'fen-0 w', san: 'e4', uci: 'e2e4', clock_s: null },
      { ply: 2, fen_before: 'fen-1 b', san: 'e5', uci: 'e7e5', clock_s: null },
    ],
    final_fen: 'fen-2 w',
    final_is_terminal: finalIsTerminal,
  }
}

const echo: Analyzer = {
  analyze: async (item: AnalysisItem, tier) => ({ ...item, tier, depth: 1, time_ms: 1, lines: [] }) as EngineResult,
}

test('scans every position plus a non-terminal final position', () => {
  expect(scanItems(game(false))).toEqual([
    { fen: 'fen-0 w', ply: 1 },
    { fen: 'fen-1 b', ply: 2 },
    { fen: 'fen-2 w', ply: 3 },
  ])
})

test('never sends a checkmate or stalemate final position to the engine', () => {
  expect(scanItems(game(true)).map((item) => item.fen)).toEqual(['fen-0 w', 'fen-1 b'])
})

test('tags verify positions with their ply', () => {
  expect(itemsForFens(game(false), ['fen-2 w', 'fen-1 b', 'fen-1 b'])).toEqual([
    { fen: 'fen-2 w', ply: 3 },
    { fen: 'fen-1 b', ply: 2 },
  ])
})

test('analyzes in order and reports progress before each item and at the end', async () => {
  const progress: [number, number, string | null][] = []

  const results = await analyzeAll(echo, scanItems(game(false)), 'scan', TIER, (done, total, item) =>
    progress.push([done, total, item?.fen ?? null]),
  )

  expect(results.map((r) => r.fen)).toEqual(['fen-0 w', 'fen-1 b', 'fen-2 w'])
  expect(progress).toEqual([
    [0, 3, 'fen-0 w'],
    [1, 3, 'fen-1 b'],
    [2, 3, 'fen-2 w'],
    [3, 3, null],
  ])
})

test.each([
  [1, 1],
  [2, 1],
  [27, 14],
  [28, 14],
])('ply %i is move %i', (ply, move) => {
  expect(moveNumber(ply)).toBe(move)
})
