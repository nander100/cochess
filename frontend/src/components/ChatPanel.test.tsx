import { act, fireEvent, render, screen } from '@testing-library/react'
import type { ChatProgress } from '../analysis/chat'
import { ChatPanel } from './ChatPanel'

function type(text: string) {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: text } })
}

test('sends a question and shows the coach answer as markdown', async () => {
  const ask = vi.fn(async () => 'You should look at **14. Nxe5**.')
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
  let finish: (reply: string) => void = () => {}
  const ask = vi.fn(
    (_message: string, onProgress: (progress: ChatProgress) => void) =>
      new Promise<string>((resolve) => {
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

  await act(async () => finish('Here is what the engine shows.'))

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
  const ask = vi.fn(async () => 'OK.')
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
