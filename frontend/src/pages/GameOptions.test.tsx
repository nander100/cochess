import { fireEvent, render, screen } from '@testing-library/react'
import { ApiError } from '../api/client'
import { DETAIL, fakeApi } from '../test/fakes'
import { ToastProvider } from '../ui'
import { GameOptions } from './GameOptions'

function setup(api = fakeApi()) {
  const onColorChanged = vi.fn()
  const onDeleted = vi.fn()
  const onLoggedOut = vi.fn()
  render(
    <ToastProvider>
      <GameOptions
        detail={DETAIL}
        api={api}
        onColorChanged={onColorChanged}
        onDeleted={onDeleted}
        onLoggedOut={onLoggedOut}
      />
    </ToastProvider>,
  )
  return { api, onColorChanged, onDeleted, onLoggedOut }
}

test('switching color asks first, says what is cleared, then reports the new game', async () => {
  const { api, onColorChanged } = setup()

  fireEvent.click(screen.getByRole('button', { name: 'I played Black' }))
  expect(screen.getByRole('alertdialog', { name: 'Change color' })).toHaveTextContent(
    "The coach's notes and your critical-moment progress",
  )
  expect(api.changeColor).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Switch to Black' }))

  await vi.waitFor(() => expect(onColorChanged).toHaveBeenCalledWith({ ...DETAIL, user_color: 'black' }))
  expect(api.changeColor).toHaveBeenCalledWith('game-1', 'black')
})

test('cancel leaves the game alone', () => {
  const { api } = setup()

  fireEvent.click(screen.getByRole('button', { name: 'Delete game' }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(api.deleteGame).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'I played Black' })).toBeInTheDocument()
})

test('deleting asks first, then leaves the page', async () => {
  const { api, onDeleted } = setup()

  fireEvent.click(screen.getByRole('button', { name: 'Delete game' }))
  expect(screen.getByRole('alertdialog', { name: 'Delete game' })).toHaveTextContent("can't be undone")
  fireEvent.click(screen.getByRole('button', { name: 'Delete game' }))

  await vi.waitFor(() => expect(onDeleted).toHaveBeenCalled())
  expect(api.deleteGame).toHaveBeenCalledWith('game-1')
})

test('a server refusal is shown in plain language, as a toast', async () => {
  const api = fakeApi({
    changeColor: vi.fn(async () => {
      throw new ApiError(409, 'That would make four games in one assessment slot.')
    }),
  })
  const { onColorChanged } = setup(api)

  fireEvent.click(screen.getByRole('button', { name: 'I played Black' }))
  fireEvent.click(screen.getByRole('button', { name: 'Switch to Black' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('four games in one assessment slot')
  expect(onColorChanged).not.toHaveBeenCalled()
})

test('export saves waiting variations first, then downloads the PGN', async () => {
  const order: string[] = []
  const api = fakeApi({
    exportPgn: vi.fn(async () => {
      order.push('export')
      return { filename: 'Alex-vs-Rival.pgn', text: '1. e4 *\n' }
    }),
  })
  const beforeExport = vi.fn(async () => {
    order.push('save')
  })
  const createObjectURL = vi.fn(() => 'blob:pgn')
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() })
  render(
    <ToastProvider>
      <GameOptions detail={DETAIL} api={api} onColorChanged={vi.fn()} onDeleted={vi.fn()} onLoggedOut={vi.fn()} beforeExport={beforeExport} />
    </ToastProvider>,
  )

  fireEvent.click(screen.getByRole('button', { name: 'Export PGN' }))

  await vi.waitFor(() => expect(click).toHaveBeenCalled())
  expect(order).toEqual(['save', 'export'])
  expect(api.exportPgn).toHaveBeenCalledWith('game-1')
  expect(click.mock.contexts[0]).toMatchObject({ download: 'Alex-vs-Rival.pgn', href: 'blob:pgn' })
  click.mockRestore()
})

test('a failed export is shown as a toast', async () => {
  const api = fakeApi({ exportPgn: vi.fn(async () => { throw new ApiError(500, 'Something went wrong.') }) })
  setup(api)

  fireEvent.click(screen.getByRole('button', { name: 'Export PGN' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')
})
