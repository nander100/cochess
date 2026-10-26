import type { CreateGameResponse, EngineResult, Tier, TierConfig } from '../api/types'
import type { AnalysisItem, Analyzer } from './StockfishEngine'

export type ProgressListener = (done: number, total: number, current: AnalysisItem | null) => void

/** Analyze positions one at a time, reporting progress before each and once at the end. */
export async function analyzeAll(
  analyzer: Analyzer,
  items: readonly AnalysisItem[],
  tierName: Tier,
  tier: TierConfig,
  onProgress: ProgressListener = () => {},
): Promise<EngineResult[]> {
  const results: EngineResult[] = []
  for (const [index, item] of items.entries()) {
    onProgress(index, items.length, item)
    results.push(await analyzer.analyze(item, tierName, tier))
  }
  onProgress(items.length, items.length, null)
  return results
}

/**
 * Every position to scan: the position before each move, then the final position unless the
 * game ended in checkmate or stalemate (the engine can't search those; the backend scores them).
 */
export function scanItems(game: CreateGameResponse): AnalysisItem[] {
  const items: AnalysisItem[] = game.positions.map((p) => ({ fen: p.fen_before, ply: p.ply }))
  if (!game.final_is_terminal) {
    items.push({ fen: game.final_fen, ply: game.positions.length + 1 })
  }
  return dedupe(items)
}

/** Items for FENs the backend asked us to verify, tagged with their ply. */
export function itemsForFens(game: CreateGameResponse, fens: readonly string[]): AnalysisItem[] {
  const plyByFen = new Map(scanItems(game).map((item) => [item.fen, item.ply]))
  return dedupe(fens.map((fen) => ({ fen, ply: plyByFen.get(fen) ?? null })))
}

/** Full move number for a ply (ply 1 = White's first move). */
export function moveNumber(ply: number): number {
  return Math.floor((ply + 1) / 2)
}

function dedupe(items: AnalysisItem[]): AnalysisItem[] {
  const seen = new Set<string>()
  const unique: AnalysisItem[] = []
  for (const item of items) {
    if (seen.has(item.fen)) continue
    seen.add(item.fen)
    unique.push(item)
  }
  return unique
}
