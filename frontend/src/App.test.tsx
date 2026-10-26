import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import { ApiError } from './api/client'
import { fakeDeps } from './test/fakes'

function submitGame() {
  fireEvent.change(screen.getByLabelText(/rating/i), { target: { value: '1350' } })
  fireEvent.change(screen.getByLabelText(/your game/i), { target: { value: '1. e4 e5 2. Nf3 *' } })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
}

test('renders the app title', () => {
  render(<App deps={fakeDeps()} />)

  expect(screen.getByRole('heading', { name: 'CoChess' })).toBeInTheDocument()
})

test('runs the analysis and shows engine details when done', async () => {
  render(<App deps={fakeDeps()} />)

  submitGame()

  expect(await screen.findByText('Analysis complete.')).toBeInTheDocument()
  expect(screen.getByText(/stockfish-19-lite, 3 thread\(s\)/)).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(1 + 4 + 2) // header + scan + verify
})

test('shows the server error when the PGN is rejected', async () => {
  const deps = fakeDeps({
    createGame: vi.fn(async () => {
      throw new ApiError(422, "Non-standard starting positions aren't supported.")
    }),
  })
  render(<App deps={deps} />)

  submitGame()

  expect(await screen.findByRole('alert')).toHaveTextContent(
    "Non-standard starting positions aren't supported.",
  )
  expect(screen.getByRole('button', { name: 'Analyze' })).toBeEnabled()
})
