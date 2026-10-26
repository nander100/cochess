// Parsing of Stockfish's UCI `info` output.

/** A score as the engine reports it: from the side to move's point of view. */
export interface UciScore {
  kind: 'cp' | 'mate'
  value: number
}

export interface InfoLine {
  depth: number
  multipv: number
  score: UciScore
  pv: string[]
}

/**
 * Parse an `info` line that carries a principal variation and an exact score.
 * Returns null for anything else: other output, `info string`, currmove updates, and
 * lowerbound/upperbound scores (those are aspiration-window bounds, not results).
 */
export function parseInfoLine(line: string): InfoLine | null {
  const tokens = line.trim().split(/\s+/)
  if (tokens[0] !== 'info') return null

  let depth: number | undefined
  let multipv = 1
  let score: UciScore | undefined
  let pv: string[] = []
  for (let i = 1; i < tokens.length; i++) {
    switch (tokens[i]) {
      case 'string':
        return null
      case 'depth':
        depth = Number(tokens[++i])
        break
      case 'multipv':
        multipv = Number(tokens[++i])
        break
      case 'score': {
        const kind = tokens[++i]
        const value = Number(tokens[++i])
        if ((kind === 'cp' || kind === 'mate') && Number.isInteger(value)) score = { kind, value }
        break
      }
      case 'lowerbound':
      case 'upperbound':
        return null
      case 'pv':
        pv = tokens.slice(i + 1)
        i = tokens.length
        break
    }
  }
  if (depth === undefined || !Number.isInteger(depth) || score === undefined || pv.length === 0) {
    return null
  }
  return { depth, multipv, score, pv }
}
