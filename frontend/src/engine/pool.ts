import type { EngineResult, Tier, TierConfig } from '../api/types'
import type { ProgressListener } from './runner'
import type { AnalysisItem, Analyzer } from './StockfishEngine'

/**
 * Several engines searching different positions at once (SPEC_V4 §8.2). Short searches use one
 * thread far better than several, so a few single-threaded engines get through a game faster
 * than one multi-threaded engine, and the single-threaded fallback build gets faster too.
 *
 * Positions are handed out in runs of consecutive moves. Each engine searches its run from the
 * end backwards, so its hash table already holds the positions that follow. An engine that fails
 * gives its unfinished positions back for the others; the analysis fails only when none are left.
 */
export async function analyzeParallel(
  analyzers: readonly Analyzer[],
  items: readonly AnalysisItem[],
  tierName: Tier,
  tier: TierConfig,
  onProgress: ProgressListener = () => {},
): Promise<EngineResult[]> {
  const results: (EngineResult | undefined)[] = new Array(items.length)
  const runs = chunks(items.length, analyzers.length)
  let done = 0
  let lastError: unknown = null
  onProgress(0, items.length, items[0] ?? null)

  async function work(analyzer: Analyzer): Promise<void> {
    for (let run = runs.shift(); run !== undefined; run = runs.shift()) {
      const pending = [...run].reverse()
      try {
        while (pending.length > 0) {
          const index = pending[0]
          results[index] = await analyzer.analyze(items[index], tierName, tier)
          pending.shift()
          done += 1
          onProgress(done, items.length, items[index])
        }
      } catch (error) {
        lastError = error
        runs.unshift(pending.reverse()) // back in game order, for whoever takes it next
        return // this engine is done for
      }
    }
  }

  await Promise.all(analyzers.map(work))
  if (done < items.length) throw lastError ?? new Error('The chess engine stopped.')
  onProgress(items.length, items.length, null)
  return results as EngineResult[]
}

/** How many single-threaded engines to run: the setting, leaving one core for the page. */
export function poolSize(setting: number, hardwareConcurrency: number): number {
  return Math.max(1, Math.min(setting, hardwareConcurrency - 1))
}

/** Index runs of consecutive positions: about two per engine, so a fast engine takes a second. */
function chunks(count: number, workers: number): number[][] {
  const size = Math.max(1, Math.ceil(count / Math.max(1, workers * 2)))
  const runs: number[][] = []
  for (let start = 0; start < count; start += size) {
    runs.push(Array.from({ length: Math.min(size, count - start) }, (_, i) => start + i))
  }
  return runs
}
