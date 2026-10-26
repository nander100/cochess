import { render, screen } from '@testing-library/react'
import { Synopsis } from './Synopsis'

test('shows that the coach is writing until text arrives', () => {
  render(<Synopsis state={{ status: 'writing', text: '', error: null }} />)

  expect(screen.getByRole('status')).toHaveTextContent('Coach is writing…')
})

test('renders the synopsis markdown', () => {
  const text = '### Overall\nA **sharp** game.\n\n### Your turn\nWhat would you play instead?'

  render(<Synopsis state={{ status: 'done', text, error: null }} />)

  expect(screen.getByRole('heading', { name: 'Overall' })).toBeInTheDocument()
  expect(screen.getByText('sharp').tagName).toBe('STRONG')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('never renders raw HTML from the model', () => {
  const text = 'Hello <img src=x onerror="alert(1)"> <script>alert(1)</script>'

  const { container } = render(<Synopsis state={{ status: 'done', text, error: null }} />)

  expect(container.querySelector('img')).toBeNull()
  expect(container.querySelector('script')).toBeNull()
})

test('shows an error', () => {
  render(<Synopsis state={{ status: 'error', text: '', error: 'The coach is unavailable.' }} />)

  expect(screen.getByRole('alert')).toHaveTextContent('The coach is unavailable.')
})
