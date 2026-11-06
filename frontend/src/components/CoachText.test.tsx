import { fireEvent, render, screen } from '@testing-library/react'
import type { LineLink, MoveToken, UserSettings } from '../api/types'
import { SettingsContext } from '../settings/settingsContext'
import { DEFAULT_SETTINGS } from '../test/fakes'
import { CoachText } from './CoachText'

const MOVE: MoveToken = { index: 0, char_offset: 4, san: 'Qxd4', words: 'queen takes on d4', move_number: 14, white: false }
const LINK: LineLink = {
  index: 0, char_offset: 40, line_id: 'line-1', ref: 'here.refutation', label: 'see why', kind: 'refutation',
  start_path_uci: ['e2e4'], moves_uci: ['e7e5', 'g1f3'],
} // prettier-ignore
const TEXT = 'Now [queen takes on d4](cc:move/0) wins a pawn: [see why](cc:line/0).'

function show(level: UserSettings['effective_detail_level'], onPlayLine = vi.fn()) {
  const settings = { ...DEFAULT_SETTINGS, effective_detail_level: level }
  render(
    <SettingsContext.Provider value={{ settings, loaded: true, update: vi.fn() }}>
      <CoachText text={TEXT} tokens={{ moves: [MOVE], line_links: [LINK] }} onPlayLine={onPlayLine} />
    </SettingsContext.Provider>,
  )
  return onPlayLine
}

test('plain shows the words only', () => {
  show('plain')
  const move = screen.getByText('queen takes on d4')
  expect(move).not.toHaveAttribute('title')
  expect(screen.queryByText(/Qxd4/)).not.toBeInTheDocument()
})

test('standard shows the words, with the notation on hover', () => {
  show('standard')
  expect(screen.getByText('queen takes on d4')).toHaveAttribute('title', '14...Qxd4')
})

test('technical shows the notation, with the words on hover', () => {
  show('technical')
  expect(screen.getByText('14...Qxd4')).toHaveAttribute('title', 'queen takes on d4')
})

test('a line link is a button that plays the line', () => {
  const onPlayLine = show('standard')

  fireEvent.click(screen.getByRole('button', { name: 'see why' }))

  expect(onPlayLine).toHaveBeenCalledWith(LINK)
})

test('without a player, a line link is plain words', () => {
  render(<CoachText text={TEXT} tokens={{ moves: [MOVE], line_links: [LINK] }} />)
  expect(screen.queryByRole('button', { name: 'see why' })).not.toBeInTheDocument()
  expect(screen.getByText('see why')).toBeInTheDocument()
})

test('words that begin a sentence are capitalized', () => {
  const settings = { ...DEFAULT_SETTINGS, effective_detail_level: 'plain' as const }
  render(
    <SettingsContext.Provider value={{ settings, loaded: true, update: vi.fn() }}>
      <CoachText text="[queen takes on d4](cc:move/0) wins." tokens={{ moves: [{ ...MOVE, sentence_start: true }] }} />
    </SettingsContext.Provider>,
  )
  expect(screen.getByText('Queen takes on d4')).toBeInTheDocument()
})
