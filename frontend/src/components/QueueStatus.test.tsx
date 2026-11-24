import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { AnalysisQueueContext } from '../analysis/analysisQueueContext'
import { ApiError } from '../api/client'
import { DETAIL, fakeDeps, fakeQueue } from '../test/fakes'
import { QueueStatus } from './QueueStatus'

function setup(hold: Promise<void> = Promise.resolve()) {
  const deps = fakeDeps({
    getGame: vi.fn(async (id: string) => {
      await hold // lets a test look at the run while it's in progress
      if (id === 'bad') throw new ApiError(500, 'broken')
      return { ...DETAIL, id, status: 'uploaded' as const }
    }),
  })
  const queue = fakeQueue(deps)
  render(
    <MemoryRouter>
      <AnalysisQueueContext.Provider value={queue}>
        <QueueStatus />
      </AnalysisQueueContext.Provider>
    </MemoryRouter>,
  )
  return queue
}

test('nothing shows while nothing is queued', () => {
  setup()

  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('a run shows its progress, then a summary that can be dismissed', async () => {
  let release = () => {}
  const queue = setup(new Promise<void>((resolve) => (release = resolve)))

  act(() => queue.add(['g1', 'bad']))

  expect(await screen.findByText(/Analyzing your imported games\./)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Game 1 of 2')
  act(() => release())
  expect(await screen.findByText(/Analyzed 1 imported game\./)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent("1 game couldn't be analyzed")

  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
