import { fireEvent, render, screen } from '@testing-library/react'
import { GameInput } from './GameInput'

function setup() {
  const onSubmit = vi.fn()
  render(<GameInput disabled={false} onSubmit={onSubmit} />)
  const analyze = () => screen.getByRole('button', { name: 'Analyze game' })
  const pgnBox = () => screen.getByLabelText(/your game/i)
  return { onSubmit, analyze, pgnBox }
}

test('no color is selected when the form loads', () => {
  setup()

  expect(screen.getByLabelText('I played White')).not.toBeChecked()
  expect(screen.getByLabelText('I played Black')).not.toBeChecked()
})

test('the PGN box and Analyze wait for a color, with a hint', () => {
  const { analyze, pgnBox } = setup()

  expect(pgnBox()).toBeDisabled()
  expect(analyze()).toBeDisabled()
  expect(screen.getByText('Choose the color you played first.')).toBeInTheDocument()
})

test('the form cannot be submitted without a color', () => {
  const { onSubmit } = setup()

  fireEvent.submit(screen.getByRole('form', { name: 'Game to analyze' }))

  expect(onSubmit).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toHaveTextContent('Choose the color you played first.')
})

test('the color comes before the PGN box', () => {
  const { pgnBox } = setup()
  const black = screen.getByLabelText('I played Black')

  expect(black.compareDocumentPosition(pgnBox()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('submits the chosen color and PGN; rating and playstyle come from the profile', () => {
  const { onSubmit, analyze, pgnBox } = setup()
  fireEvent.click(screen.getByLabelText('I played Black'))
  fireEvent.change(pgnBox(), { target: { value: '1. e4 e5 *' } })

  expect(screen.queryByText('Choose the color you played first.')).not.toBeInTheDocument()
  fireEvent.click(analyze())

  expect(onSubmit).toHaveBeenCalledWith({ pgn: '1. e4 e5 *', user_color: 'black' })
  expect(screen.queryByLabelText(/rating/i)).not.toBeInTheDocument()
})

test('asks for a PGN when the box is empty', () => {
  const { onSubmit, analyze } = setup()
  fireEvent.click(screen.getByLabelText('I played White'))

  fireEvent.click(analyze())

  expect(screen.getByRole('alert')).toHaveTextContent('Paste the game')
  expect(onSubmit).not.toHaveBeenCalled()
})
