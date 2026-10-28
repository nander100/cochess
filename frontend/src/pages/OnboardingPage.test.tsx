import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, test, vi } from 'vitest'
import App from '../App'
import type { PipelineDeps } from '../analysis/pipeline'
import type { GameChoice, OnboardingGame, OnboardingStatus, ParsedRow, ParseResponse } from '../api/types'
import { DETAIL, EMPTY_ONBOARDING, EMPTY_SLOTS, REPORT_TEXT, fakeDeps } from '../test/fakes'

vi.mock('../board/Board', () => ({ Board: () => <div data-testid="board" /> }))

function renderAt(deps: PipelineDeps, path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App deps={deps} />
    </MemoryRouter>,
  )
}

function row(index: number, overrides: Partial<ParsedRow> = {}): ParsedRow {
  return {
    index,
    pgn: `[White "me"]\n\n1. e4 e5 1-0`,
    white: 'me',
    black: `Opponent ${index}`,
    result: '1-0',
    date: '2026.10.01',
    time_control: '600',
    category: 'rapid',
    error: null,
    suggested_color: 'white',
    user_color: 'white',
    user_result: 'win',
    slot: 'white_win',
    reason: null,
    ...overrides,
  }
}

function game(id: string, status: OnboardingGame['status']): OnboardingGame {
  return { id, slot: 'white_win', status, opponent: 'Opponent 0', played_at: '2026-10-01T00:00:00Z', opening: null }
}

const FULL = EMPTY_SLOTS.map((slot) => ({ ...slot, filled: 3 }))

function ready(report: OnboardingStatus['report'] = null): OnboardingStatus {
  const games = Array.from({ length: 12 }, (_, i) => game(`g${i}`, 'analyzed'))
  return { ...EMPTY_ONBOARDING, slots: FULL, games, complete: true, analyzed: 12, report_ready: true, report }
}

describe('adding games', () => {
  test('the paste becomes a table; the player settles each game; usable games are added', async () => {
    const draw = row(1, { result: '1/2-1/2', user_result: 'draw', slot: null, reason: 'draw' })
    const noTc = row(2, { category: null, time_control: null, slot: null, reason: 'needs_time_control' })
    const parsed = (choices: (GameChoice | null)[]): ParseResponse => ({
      primary_time_control: 'rapid',
      slots: EMPTY_SLOTS,
      games: [
        row(0),
        draw,
        choices[2]?.time_control_category ? { ...noTc, slot: 'white_win', reason: null } : noTc,
      ],
    })
    const deps = fakeDeps({
      onboardingParse: vi.fn(async (_text: string, choices: (GameChoice | null)[]) => parsed(choices)),
      onboardingSubmit: vi.fn(async () => ({
        results: [
          { index: 0, slot: 'white_win' as const, reason: null, game_id: 'new-1' },
          { index: 1, slot: 'white_win' as const, reason: null, game_id: 'new-2' },
        ],
        slots: EMPTY_SLOTS,
      })),
    })
    renderAt(deps, '/onboarding')

    fireEvent.change(await screen.findByLabelText(/Paste one or more games/), { target: { value: 'three games' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check games' }))

    const table = await screen.findByRole('table')
    expect(within(table).getByText("Draws don't fill a slot.")).toBeInTheDocument()
    expect(within(table).getByText('Choose the time control.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add 1 game' })).toBeEnabled()

    fireEvent.change(screen.getByLabelText('Time control for game 3'), { target: { value: 'rapid' } })

    const add = await screen.findByRole('button', { name: 'Add 2 games' })
    expect(vi.mocked(deps.api.onboardingParse).mock.calls.at(-1)![1][2]).toEqual({ time_control_category: 'rapid' })
    fireEvent.click(add)

    expect(await screen.findByText('Added 2 games.')).toBeInTheDocument()
    const sent = vi.mocked(deps.api.onboardingSubmit).mock.calls[0][0]
    expect(sent.map((g) => [g.user_color, g.time_control_category])).toEqual([
      ['white', null],
      ['white', 'rapid'],
    ])
  })

  test('the player can change the suggested color', async () => {
    const deps = fakeDeps({
      onboardingParse: vi.fn(async (_text: string, choices: (GameChoice | null)[]) => ({
        primary_time_control: 'rapid' as const,
        slots: EMPTY_SLOTS,
        games: [choices[0]?.user_color === 'black' ? row(0, { user_color: 'black', user_result: 'loss', slot: 'black_loss' }) : row(0)],
      })),
    })
    renderAt(deps, '/onboarding')
    fireEvent.change(await screen.findByLabelText(/Paste one or more games/), { target: { value: 'a game' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check games' }))

    fireEvent.change(await screen.findByLabelText('Your color in game 1'), { target: { value: 'black' } })

    expect(await screen.findByText('Black loss')).toBeInTheDocument()
  })
})

describe('analysis', () => {
  test('waiting games are analyzed when the page opens, with progress, resuming from the server', async () => {
    const statuses = [
      { ...EMPTY_ONBOARDING, games: [game('g1', 'uploaded')], analyzed: 0 },
      { ...EMPTY_ONBOARDING, games: [game('g1', 'uploaded')], analyzed: 0 },
      { ...EMPTY_ONBOARDING, games: [game('g1', 'analyzed')], analyzed: 1 },
    ]
    const deps = fakeDeps({
      onboardingStatus: vi.fn(async () => statuses.shift() ?? { ...EMPTY_ONBOARDING, games: [game('g1', 'analyzed')], analyzed: 1 }),
      getGame: vi.fn(async () => ({ ...DETAIL, id: 'g1', status: 'uploaded' as const })),
    })
    renderAt(deps, '/onboarding')

    expect(await screen.findByText('Games (1 of 1 analyzed)')).toBeInTheDocument()
    expect(deps.api.submitScan).toHaveBeenCalledWith('g1', expect.any(Array))
    expect(deps.api.submitVerify).toHaveBeenCalledWith('g1', expect.any(Array))
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/games/g1')
  })

  test('a failed analysis can be continued', async () => {
    const deps = fakeDeps({
      onboardingStatus: vi.fn(async () => ({ ...EMPTY_ONBOARDING, games: [game('g1', 'uploaded')] })),
      getGame: vi.fn(async () => {
        throw new Error('The engine crashed.')
      }),
    })
    renderAt(deps, '/onboarding')

    expect(await screen.findByText('The engine crashed.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Continue analysis (1 left)' })).toBeInTheDocument()
  })
})

describe('the baseline report', () => {
  test('is written when all 12 games are analyzed', async () => {
    const deps = fakeDeps({ onboardingStatus: vi.fn(async () => ready()) })
    renderAt(deps, '/onboarding')

    fireEvent.click(await screen.findByRole('button', { name: 'Write my baseline report' }))

    expect(await screen.findByText('You are a solid rapid player.')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Paste one or more games/)).not.toBeInTheDocument()
  })

  test('a stored report is shown on the onboarding page and the profile', async () => {
    const report = { text: REPORT_TEXT, invalid_moves_removed: [], game_ids: [], created_at: '2026-10-27T10:00:00Z' }
    const deps = fakeDeps({
      onboardingStatus: vi.fn(async () => ready(report)),
      baselineReport: vi.fn(async () => report),
    })
    renderAt(deps, '/onboarding')
    expect(await screen.findByText('You are a solid rapid player.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Write my baseline report' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Profile' }))

    const panel = await screen.findByRole('region', { name: 'Baseline report' })
    await waitFor(() => expect(within(panel).getByText('You are a solid rapid player.')).toBeInTheDocument())
  })

  test('the profile points to the assessment before there is a report', async () => {
    renderAt(fakeDeps(), '/profile')

    expect(await screen.findByRole('link', { name: 'Add your 12 assessment games' })).toHaveAttribute('href', '/onboarding')
  })
})
