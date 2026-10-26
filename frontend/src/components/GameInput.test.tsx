import { fireEvent, render, screen } from '@testing-library/react'
import { GameInput } from './GameInput'

function setup() {
  const onSubmit = vi.fn()
  render(<GameInput disabled={false} onSubmit={onSubmit} />)
  const submit = () => fireEvent.click(screen.getByRole('button', { name: 'Analyze' }))
  return { onSubmit, submit }
}

test('submits the color and PGN; rating and playstyle come from the profile', () => {
  const { onSubmit, submit } = setup()
  fireEvent.click(screen.getByLabelText('Black'))
  fireEvent.change(screen.getByLabelText(/your game/i), { target: { value: '1. e4 e5 *' } })

  submit()

  expect(onSubmit).toHaveBeenCalledWith({ pgn: '1. e4 e5 *', user_color: 'black' })
  expect(screen.queryByLabelText(/rating/i)).not.toBeInTheDocument()
})

test('asks for a PGN when the box is empty', () => {
  const { onSubmit, submit } = setup()

  submit()

  expect(screen.getByRole('alert')).toHaveTextContent('Paste the game')
  expect(onSubmit).not.toHaveBeenCalled()
})
