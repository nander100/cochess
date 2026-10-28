import { describe, expect, it, vi } from 'vitest'
import type { OnboardingGame, OnboardingStatus } from '../api/types'
import { DETAIL, EMPTY_ONBOARDING, fakeDeps } from '../test/fakes'
import { type QueueProgress, queueLabel, runOnboardingQueue } from './queue'

function game(id: string, status: OnboardingGame['status']): OnboardingGame {
  return { id, slot: 'white_win', status, opponent: 'X', played_at: '2026-10-01T00:00:00Z', opening: null }
}

function statusWith(...games: OnboardingGame[]): OnboardingStatus {
  return { ...EMPTY_ONBOARDING, games, analyzed: games.filter((g) => g.status === 'analyzed').length }
}

describe('runOnboardingQueue', () => {
  it('analyzes the games not yet analyzed, in order, resuming from the server status', async () => {
    const statuses = [
      statusWith(game('a', 'analyzed'), game('b', 'scanned'), game('c', 'uploaded')),
      statusWith(game('a', 'analyzed'), game('b', 'analyzed'), game('c', 'uploaded')),
      statusWith(game('a', 'analyzed'), game('b', 'analyzed'), game('c', 'analyzed')),
    ]
    const deps = fakeDeps({
      onboardingStatus: vi.fn(async () => statuses.shift() ?? statusWith()),
      getGame: vi.fn(async (id: string) =>
        id === 'b' ? { ...DETAIL, id, status: 'scanned' as const, verify_fens: ['fen-1 b'] } : { ...DETAIL, id, status: 'uploaded' as const },
      ),
    })
    const progress: QueueProgress[] = []

    const final = await runOnboardingQueue(deps, (p) => progress.push(p))

    expect(final.analyzed).toBe(3)
    expect(vi.mocked(deps.api.getGame).mock.calls.map(([id]) => id)).toEqual(['b', 'c'])
    // Game b's scan was stored: only its verify step ran. Game c ran both.
    expect(vi.mocked(deps.api.submitScan).mock.calls.map(([id]) => id)).toEqual(['c'])
    expect(vi.mocked(deps.api.submitVerify).mock.calls.map(([id]) => id)).toEqual(['b', 'c'])
    expect(new Set(progress.map((p) => `${p.game}/${p.total}`))).toEqual(new Set(['2/3', '3/3']))
  })

  it('stops instead of looping when a game stays unanalyzed', async () => {
    const deps = fakeDeps({ onboardingStatus: vi.fn(async () => statusWith(game('a', 'uploaded'))) })

    await expect(runOnboardingQueue(deps, () => {})).rejects.toThrow("Game 1 couldn't be analyzed")
  })

  it('does nothing when every game is analyzed', async () => {
    const deps = fakeDeps({ onboardingStatus: vi.fn(async () => statusWith(game('a', 'analyzed'))) })

    await runOnboardingQueue(deps, () => {})

    expect(deps.api.engineConfig).not.toHaveBeenCalled()
  })
})

describe('queueLabel', () => {
  it('names the game and the move', () => {
    const scanning = { phase: 'scanning' as const, done: 13, total: 76, moveNumber: 14, totalMoves: 38 }

    expect(queueLabel({ game: 3, total: 12, status: scanning })).toBe('Game 3 of 12 — move 14 of 38')
    expect(queueLabel({ game: 3, total: 12, status: { phase: 'verifying', done: 1, total: 6 } })).toBe(
      'Game 3 of 12 — double-checking key moments (2 of 6)',
    )
  })
})

describe('progress', () => {
  it('reports the server status before each game, so the count goes up as games finish', async () => {
    const statuses = [
      statusWith(game('a', 'uploaded'), game('b', 'uploaded')),
      statusWith(game('a', 'analyzed'), game('b', 'uploaded')),
      statusWith(game('a', 'analyzed'), game('b', 'analyzed')),
    ]
    const deps = fakeDeps({
      onboardingStatus: vi.fn(async () => statuses.shift() ?? statusWith()),
      getGame: vi.fn(async (id: string) => ({ ...DETAIL, id, status: 'uploaded' as const })),
    })
    const seen: number[] = []

    await runOnboardingQueue(deps, () => {}, (status) => seen.push(status.analyzed))

    expect(seen).toEqual([0, 1, 2])
  })
})
