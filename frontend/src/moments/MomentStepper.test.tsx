import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { BeforeSearches } from '../analysis/moments'
import type { ApiClient } from '../api/client'
import type { CoachEvent } from '../api/sse'
import type { MomentInfo } from '../api/types'
import { DETAIL, MOMENT, fakeApi } from '../test/fakes'
import { MomentStepper } from './MomentStepper'

const FEN = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2'
const INTRO = { role: 'coach' as const, text: 'What would you play instead?', kind: 'intro' }

/** The stepper with a parent that keeps the server's record, as the game page does. */
function Harness({ initial, api, onUpdated }: { initial: MomentInfo[]; api: ApiClient; onUpdated: (m: MomentInfo[]) => void }) {
  const [moments, setMoments] = useState(initial)
  return (
    <MomentStepper
      gameId="game-1"
      moments={moments}
      current={moments[0].index}
      onSelect={vi.fn()}
      fen={FEN}
      candidate={null}
      onTakeBack={vi.fn()}
      deps={{ api, analyzeDeep: vi.fn() }}
      searches={new BeforeSearches()}
      onUpdated={(fresh) => {
        onUpdated(fresh)
        setMoments(fresh)
      }}
      onLoggedOut={vi.fn()}
    />
  )
}

function renderStepper(moments: MomentInfo[], api = fakeApi()) {
  const onUpdated = vi.fn()
  render(<Harness initial={moments} api={api} onUpdated={onUpdated} />)
  return { api, onUpdated }
}

test('a question goes to the moment and the server record replaces the pending messages', async () => {
  const open = { ...MOMENT, state: 'intro' as const, messages: [INTRO] }
  const asked = {
    ...open,
    messages: [
      INTRO,
      { role: 'player' as const, text: 'A hint?', kind: 'question' },
      { role: 'coach' as const, text: 'Think about the centre.', kind: 'answer' },
    ],
  }
  const api = fakeApi({ getGame: vi.fn(async () => ({ ...DETAIL, moments: [asked] })) })
  const { onUpdated } = renderStepper([open], api)

  fireEvent.change(screen.getByLabelText('Ask the coach about this moment'), { target: { value: 'A hint?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

  expect(await screen.findByText('Think about the centre.')).toBeInTheDocument()
  expect(api.momentAsk).toHaveBeenCalledWith('game-1', 1, 'A hint?', expect.any(Function))
  await vi.waitFor(() => expect(onUpdated).toHaveBeenCalledWith([asked]))
  expect(screen.getByText('Think about the centre.')).toBeInTheDocument() // now from the record
})

test('wrap-up is offered only once every moment is finished', () => {
  const second = { ...MOMENT, index: 2, ply: 5, move_number: 3, san: 'Bb5' }
  renderStepper([{ ...MOMENT, state: 'solved' }, second])

  expect(screen.queryByRole('button', { name: 'Wrap up' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next moment' })).toBeInTheDocument()
})

test('the stored wrap-up is shown after the last moment', () => {
  const done = { ...MOMENT, state: 'revealed' as const, messages: [INTRO, { role: 'coach' as const, text: 'Well done overall.', kind: 'wrap_up' }] }

  renderStepper([done])

  expect(screen.getByText('Well done overall.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Wrap up' })).not.toBeInTheDocument()
})

test('a coach error is shown and nothing is lost', async () => {
  const api = fakeApi({
    momentStart: vi.fn(async (_gameId: string, _index: number, onEvent: (event: CoachEvent) => void) => {
      onEvent({ type: 'error', message: 'The coach is unavailable right now.' })
    }),
  })
  const { onUpdated } = renderStepper([MOMENT], api)

  fireEvent.click(screen.getByRole('button', { name: 'Start this moment' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('The coach is unavailable right now.')
  expect(onUpdated).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Start this moment' })).toBeEnabled()
})
