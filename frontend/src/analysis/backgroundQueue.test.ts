import { ApiError } from '../api/client'
import type { GameDetail } from '../api/types'
import { DETAIL, fakeDeps } from '../test/fakes'
import { AnalysisQueue, type QueueState, type QueueStorage } from './backgroundQueue'

function memoryStorage(initial: string[] = []): QueueStorage & { saved: string[] } {
  const store = { saved: [...initial] }
  return Object.assign(store, {
    load: () => [...store.saved],
    save: (ids: string[]) => {
      store.saved = [...ids]
    },
  })
}

/** Fake games: `uploaded` ones get analyzed, `analyzed` ones are skipped, `broken` ones fail. */
function deps(games: Record<string, 'uploaded' | 'analyzed' | 'broken' | 'logged-out'>) {
  return fakeDeps({
    getGame: vi.fn(async (id: string): Promise<GameDetail> => {
      const kind = games[id]
      if (kind === 'logged-out') throw new ApiError(401, "You're not logged in.")
      if (kind === 'broken') throw new ApiError(500, 'Something broke.')
      return { ...DETAIL, id, status: kind === 'analyzed' ? 'analyzed' : 'uploaded' }
    }),
  })
}

async function settled(queue: AnalysisQueue): Promise<QueueState> {
  await vi.waitFor(() => expect(queue.state.running).toBe(false))
  return queue.state
}

test('added games are analyzed in order and leave the queue as they finish', async () => {
  const d = deps({ g1: 'uploaded', g2: 'uploaded' })
  const storage = memoryStorage()
  const queue = new AnalysisQueue(d, storage)

  queue.add(['g1', 'g2'])
  const state = await settled(queue)

  expect(state.finished).toEqual(['g1', 'g2'])
  expect(state.pending).toEqual([])
  expect(state.failed).toEqual([])
  expect(storage.saved).toEqual([])
  expect(d.api.submitScan).toHaveBeenCalledTimes(2)
})

test('subscribers hear each game finish, and progress says which game of how many', async () => {
  const queue = new AnalysisQueue(deps({ g1: 'uploaded', g2: 'uploaded', g3: 'uploaded' }), memoryStorage())
  const seen: Array<[number, number]> = []
  const finishedCounts: number[] = []
  queue.subscribe((state) => {
    if (state.progress) seen.push([state.progress.game, state.progress.total])
    finishedCounts.push(state.finished.length)
  })

  queue.add(['g1', 'g2', 'g3'])
  await settled(queue)

  expect(seen[0]).toEqual([1, 3])
  expect(seen.at(-1)).toEqual([3, 3])
  expect(finishedCounts.at(-1)).toBe(3)
})

test('a game already analyzed is skipped without searching', async () => {
  const d = deps({ g1: 'analyzed' })
  const queue = new AnalysisQueue(d, memoryStorage())

  queue.add(['g1'])
  const state = await settled(queue)

  expect(state.finished).toEqual(['g1'])
  expect(d.engine.analyze).not.toHaveBeenCalled()
})

test('a game that fails is set aside and the rest carry on', async () => {
  const queue = new AnalysisQueue(deps({ g1: 'broken', g2: 'uploaded' }), memoryStorage())

  queue.add(['g1', 'g2'])
  const state = await settled(queue)

  expect(state.failed).toEqual(['g1'])
  expect(state.finished).toEqual(['g2'])
})

test('being logged out stops the queue and keeps what is left for later', async () => {
  const storage = memoryStorage()
  const queue = new AnalysisQueue(deps({ g1: 'logged-out', g2: 'uploaded' }), storage)

  queue.add(['g1', 'g2'])
  const state = await settled(queue)

  expect(state.loggedOut).toBe(true)
  expect(state.pending).toEqual(['g1', 'g2'])
  expect(storage.saved).toEqual(['g1', 'g2'])
})

test('a reload picks up where the queue stopped', async () => {
  const storage = memoryStorage(['g2', 'g3'])
  const queue = new AnalysisQueue(deps({ g2: 'uploaded', g3: 'uploaded' }), storage)

  expect(queue.state.pending).toEqual(['g2', 'g3'])
  queue.resume()
  const state = await settled(queue)

  expect(state.finished).toEqual(['g2', 'g3'])
  expect(storage.saved).toEqual([])
})

test('a game added twice is queued once, and games added mid-run join the same run', async () => {
  const d = deps({ g1: 'uploaded', g2: 'uploaded', g3: 'uploaded' })
  const queue = new AnalysisQueue(d, memoryStorage())

  queue.add(['g1', 'g2'])
  queue.add(['g2', 'g3'])
  const state = await settled(queue)

  expect(state.finished).toEqual(['g1', 'g2', 'g3'])
  expect(d.api.getGame).toHaveBeenCalledTimes(3)
})

test('clearing forgets everything (signing out)', () => {
  const storage = memoryStorage(['g1'])
  const queue = new AnalysisQueue(deps({}), storage)

  queue.clear()

  expect(queue.state.pending).toEqual([])
  expect(storage.saved).toEqual([])
})
