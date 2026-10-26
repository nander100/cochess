import { fireEvent, render, screen } from '@testing-library/react'
import { GameInput } from './GameInput'

function setup() {
  const onSubmit = vi.fn()
  render(<GameInput disabled={false} onSubmit={onSubmit} />)
  const fill = (label: RegExp, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
  return { onSubmit, fill, submit }
}

test('submits the profile and PGN, trimming an empty playstyle to null', () => {
  const { onSubmit, fill, submit } = setup()
  fill(/rating/i, '1350')
  fireEvent.click(screen.getByLabelText('Black'))
  fill(/how do you like to play/i, '   ')
  fill(/your game/i, '1. e4 e5 *')

  submit()

  expect(onSubmit).toHaveBeenCalledWith({
    pgn: '1. e4 e5 *',
    user_color: 'black',
    elo: 1350,
    playstyle: null,
  })
})

test.each(['', '99', '3001', '1200.5'])('rejects Elo %j with a clear message', (elo) => {
  const { onSubmit, fill, submit } = setup()
  fill(/rating/i, elo)
  fill(/your game/i, '1. e4 *')

  submit()

  expect(screen.getByRole('alert')).toHaveTextContent('whole number from 100 to 3000')
  expect(onSubmit).not.toHaveBeenCalled()
})

test('asks for a PGN when the box is empty', () => {
  const { onSubmit, fill, submit } = setup()
  fill(/rating/i, '1350')

  submit()

  expect(screen.getByRole('alert')).toHaveTextContent('Paste the game')
  expect(onSubmit).not.toHaveBeenCalled()
})

test('limits the playstyle description to 500 characters', () => {
  setup()

  expect(screen.getByLabelText(/how do you like to play/i)).toHaveAttribute('maxLength', '500')
})
