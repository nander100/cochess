import { act, fireEvent, render, screen } from '@testing-library/react'
import type { ChatProgress } from '../analysis/chat'
import type { Annotation, CoachReply } from '../api/types'
import { ChatPanel } from './ChatPanel'

function reply(text: string, annotations: Annotation[] = []): CoachReply {
  return { text, annotations }
}

const TAG: Annotation = {
  tag_index: 0,
  char_offset: 12,
  arrows: [{ orig: 'c4', dest: 'f7', color: 'red' }],
  squares: [],
}

function type(text: string) {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: text } })
}

test('sends a question and shows the coach answer as markdown', async () => {
  const ask = vi.fn(async () => reply('You should look at **14. Nxe5**.'))
  render(<ChatPanel ask={ask} />)

  type('  What about move 14?  ')
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByText('14. Nxe5')).toHaveProperty('tagName', 'STRONG')
  expect(screen.getByText('What about move 14?')).toBeInTheDocument()
  expect(ask).toHaveBeenCalledWith('What about move 14?', expect.any(Function))
  expect(screen.getByLabelText('Your question')).toHaveValue('')
})

test('shows that the coach is thinking deeply during an engine analysis', async () => {
  let report: (progress: ChatProgress) => void = () => {}
  let finish: (value: CoachReply) => void = () => {}
  const ask = vi.fn(
    (_message: string, onProgress: (progress: ChatProgress) => void) =>
      new Promise<CoachReply>((resolve) => {
        report = onProgress
        finish = resolve
      }),
  )
  render(<ChatPanel ask={ask} />)
  type('What if Nxe5?')
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  act(() => report('thinking'))

  expect(screen.getByRole('status')).toHaveTextContent('Coach is thinking deeply…')
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

  await act(async () => finish(reply('Here is what the engine shows.')))

  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Here is what the engine shows.')).toBeInTheDocument()
})

test('shows an error and lets the player try again', async () => {
  const ask = vi.fn(async () => {
    throw new Error("You've reached the limit of 30 questions for this game.")
  })
  render(<ChatPanel ask={ask} />)

  type('One more?')
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('limit of 30 questions')
  type('Again?')
  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
})

test('Enter sends, Shift+Enter does not', async () => {
  const ask = vi.fn(async () => reply('OK.'))
  render(<ChatPanel ask={ask} />)
  const box = screen.getByLabelText('Your question')

  type('First line')
  fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
  expect(ask).not.toHaveBeenCalled()

  fireEvent.keyDown(box, { key: 'Enter' })

  expect(await screen.findByText('OK.')).toBeInTheDocument()
  expect(ask).toHaveBeenCalledOnce()
})

test('blank messages cannot be sent', () => {
  render(<ChatPanel ask={vi.fn()} />)

  type('   ')

  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
})

test('a board tag shows as an icon; hovering it shows that tag, clicking it goes there', async () => {
  const ask = vi.fn(async () => reply('The bishop [board](cc:board/0) eyes f7.', [TAG]))
  const onReply = vi.fn()
  const onShowTag = vi.fn()
  render(<ChatPanel ask={ask} path="e2e4 e7e5" onReply={onReply} onShowTag={onShowTag} />)
  type('What is White threatening?')
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  const tag = await screen.findByRole('button', { name: 'Show this on the board' })
  expect(onReply).toHaveBeenCalledWith('e2e4 e7e5', [TAG])
  expect(screen.getByText(/eyes f7/)).toBeInTheDocument()
  expect(screen.queryByText('board')).not.toBeInTheDocument()

  fireEvent.mouseEnter(tag)
  fireEvent.mouseLeave(tag)
  fireEvent.click(tag)

  expect(onShowTag.mock.calls).toEqual([
    ['e2e4 e7e5', TAG, 'hover'],
    ['e2e4 e7e5', null, 'hover'],
    ['e2e4 e7e5', TAG, 'click'],
  ])
})

test('a stored conversation keeps its board tags and their position', () => {
  const onShowTag = vi.fn()
  render(
    <ChatPanel
      ask={vi.fn()}
      onShowTag={onShowTag}
      initial={[{ role: 'coach', text: 'Look [board](cc:board/0) here.', path: '', annotations: [TAG] }]}
    />,
  )

  fireEvent.click(screen.getByRole('button', { name: 'Show this on the board' }))

  expect(onShowTag).toHaveBeenCalledWith('', TAG, 'click')
})

test('ordinary links in coach text still work, and a placeholder with no tag shows nothing', async () => {
  const ask = vi.fn(async () => reply('Read [the rules](https://lichess.org/rules) [board](cc:board/3).'))
  render(<ChatPanel ask={ask} />)
  type('Rules?')
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(await screen.findByRole('link', { name: 'the rules' })).toHaveAttribute('href', 'https://lichess.org/rules')
  expect(screen.queryByRole('button', { name: 'Show this on the board' })).not.toBeInTheDocument()
})
