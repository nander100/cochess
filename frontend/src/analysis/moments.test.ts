import { describe, expect, it, vi } from 'vitest'
import type { CoachEvent } from '../api/sse'
import type { EngineResult } from '../api/types'
import { coachSays, fakeApi } from '../test/fakes'
import { BeforeSearches, type MomentDeps, coachStep, fenAfter, sanOf, showMe, tryMove } from './moments'

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
// Fool's mate: after 1. f3 e5 2. g4, Black mates with Qh4#.
const FOOLS = 'rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2'

function deep(fen: string): EngineResult {
  return { ply: null, fen, tier: 'deep', depth: 22, time_ms: 3000, lines: [{ rank: 1, eval_cp: 20, mate: null, moves_uci: ['e2e4'] }] }
}

function deps(): MomentDeps {
  return { api: fakeApi(), analyzeDeep: vi.fn(async (fen: string) => deep(fen)) }
}

describe('moves', () => {
  it('plays a legal move and names it', () => {
    expect(fenAfter(START, 'g1f3')).toBe('rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1')
    expect(sanOf(START, 'g1f3')).toBe('Nf3')
  })

  it('rejects an illegal move', () => {
    expect(fenAfter(START, 'e2e5')).toBeNull()
    expect(sanOf(START, 'e2e5')).toBe('e2e5')
  })
})

describe('tryMove', () => {
  it('searches before and after the move, then sends both with the reasoning', async () => {
    const d = deps()
    const progress: string[] = []

    const reply = await tryMove(d, new BeforeSearches(), 'g1', 1, START, 'g1f3', '  develop  ', (p) => progress.push(p))

    expect(reply).toEqual({ text: 'Not quite. Look at your queen.', grade: 'mistake', state: 'attempt' })
    expect(progress).toEqual(['checking', 'writing'])
    const [, index, body] = vi.mocked(d.api.momentAttempt).mock.calls[0]
    expect(index).toBe(1)
    expect(body.move_uci).toBe('g1f3')
    expect(body.reasoning).toBe('develop')
    expect(body.engine_before?.fen).toBe(START)
    expect(body.engine_after?.fen).toBe(fenAfter(START, 'g1f3'))
  })

  it('searches the moment position once per visit', async () => {
    const d = deps()
    const searches = new BeforeSearches()

    await tryMove(d, searches, 'g1', 1, START, 'g1f3', '', () => {})
    await tryMove(d, searches, 'g1', 1, START, 'b1c3', '', () => {})

    const fens = vi.mocked(d.analyzeDeep).mock.calls.map(([fen]) => fen)
    expect(fens.filter((fen) => fen === START)).toHaveLength(1)
    expect(vi.mocked(d.api.momentAttempt).mock.calls[1][2].reasoning).toBeUndefined()
  })

  it("doesn't search after a move that ends the game", async () => {
    const d = deps()

    await tryMove(d, new BeforeSearches(), 'g1', 1, FOOLS, 'd8h4', '', () => {})

    expect(d.analyzeDeep).toHaveBeenCalledTimes(1)
    expect(vi.mocked(d.api.momentAttempt).mock.calls[0][2].engine_after).toBeUndefined()
  })

  it('refuses an illegal move before searching', async () => {
    const d = deps()

    await expect(tryMove(d, new BeforeSearches(), 'g1', 1, START, 'e2e5', '', () => {})).rejects.toThrow('legal')
    expect(d.analyzeDeep).not.toHaveBeenCalled()
  })

  it('searches again after a failed search', async () => {
    const d = deps()
    vi.mocked(d.analyzeDeep).mockRejectedValueOnce(new Error('engine crashed'))
    const searches = new BeforeSearches()

    await expect(tryMove(d, searches, 'g1', 1, START, 'g1f3', '', () => {})).rejects.toThrow('engine crashed')
    await tryMove(d, searches, 'g1', 1, START, 'g1f3', '', () => {})

    expect(d.api.momentAttempt).toHaveBeenCalledTimes(1)
  })
})

describe('coach steps', () => {
  it('reveals with the position search', async () => {
    const d = deps()

    const reply = await showMe(d, new BeforeSearches(), 'g1', 2, START, () => {})

    expect(reply.state).toBe('revealed')
    expect(vi.mocked(d.api.momentReveal).mock.calls[0][2]?.fen).toBe(START)
  })

  it('surfaces a coach error', async () => {
    const run = async (onEvent: (event: CoachEvent) => void) => {
      onEvent({ type: 'error', message: 'The coach is busy.' })
    }

    await expect(coachStep(run, () => {})).rejects.toThrow('The coach is busy.')
  })

  it('treats a stream without done as lost', async () => {
    const run = async (onEvent: (event: CoachEvent) => void) => {
      onEvent({ type: 'text', text: 'half an ans' })
    }

    await expect(coachStep(run, () => {})).rejects.toThrow('lost')
  })

  it('returns plain text with no grade', async () => {
    const reply = await coachStep(coachSays('Hello.'), () => {})

    expect(reply).toEqual({ text: 'Hello.', grade: null, state: null })
  })
})
