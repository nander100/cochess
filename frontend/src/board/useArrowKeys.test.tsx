import { fireEvent, render, screen } from '@testing-library/react'
import { useArrowKeys } from './useArrowKeys'

function setup() {
  const back = vi.fn()
  const forward = vi.fn()
  function Harness() {
    useArrowKeys(back, forward)
    return (
      <>
        <input type="checkbox" aria-label="Engine" />
        <input type="text" aria-label="Name" />
        <textarea aria-label="Question" />
      </>
    )
  }
  render(<Harness />)
  return { back, forward }
}

test('← and → step back and forward', () => {
  const { back, forward } = setup()

  fireEvent.keyDown(window, { key: 'ArrowLeft' })
  fireEvent.keyDown(window, { key: 'ArrowRight' })

  expect(back).toHaveBeenCalledOnce()
  expect(forward).toHaveBeenCalledOnce()
})

test('arrow keys still step through moves while a checkbox has focus', () => {
  const { forward } = setup()

  fireEvent.keyDown(screen.getByLabelText('Engine'), { key: 'ArrowRight' })

  expect(forward).toHaveBeenCalledOnce()
})

test('arrow keys are left alone while the player types', () => {
  const { back, forward } = setup()

  fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'ArrowLeft' })
  fireEvent.keyDown(screen.getByLabelText('Question'), { key: 'ArrowRight' })
  fireEvent.keyDown(window, { key: 'ArrowRight', ctrlKey: true })

  expect(back).not.toHaveBeenCalled()
  expect(forward).not.toHaveBeenCalled()
})
