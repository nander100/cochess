import { act, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { MemoryRouter } from 'react-router'
import {
  Button,
  ChatBubble,
  EmptyState,
  ErrorState,
  Header,
  IconButton,
  Modal,
  ProgressBar,
  SegmentedToggle,
  StepChips,
  TOAST_MS,
  Tabs,
  ToastProvider,
  Tooltip,
  useToast,
} from '.'
import { CloseIcon } from './icons'

describe('buttons', () => {
  test('a disabled button says so to assistive tech and keeps its label', () => {
    render(<Button disabled>Analyze</Button>)

    const button = screen.getByRole('button', { name: 'Analyze' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  test('an icon button is named by its label', () => {
    const onClick = vi.fn()
    render(<IconButton label="Flip board" icon={<CloseIcon />} onClick={onClick} />)

    fireEvent.click(screen.getByRole('button', { name: 'Flip board' }))

    expect(onClick).toHaveBeenCalled()
  })
})

describe('segmented toggle', () => {
  function Color() {
    const [value, setValue] = useState<'white' | 'black' | null>(null)
    return (
      <SegmentedToggle
        legend="Which color did you play?"
        options={[
          { value: 'white', label: 'I played White' },
          { value: 'black', label: 'I played Black' },
        ]}
        value={value}
        onChange={setValue}
      />
    )
  }

  test('starts with nothing selected and acts as one choice', () => {
    render(<Color />)
    const white = screen.getByLabelText('I played White')
    const black = screen.getByLabelText('I played Black')
    expect(white).not.toBeChecked()
    expect(black).not.toBeChecked()

    fireEvent.click(black)

    expect(black).toBeChecked()
    expect(white).not.toBeChecked()
    expect(screen.getByRole('group', { name: 'Which color did you play?' })).toBeInTheDocument()
  })
})

describe('tabs', () => {
  function Panel() {
    const [tab, setTab] = useState<'coach' | 'moments'>('coach')
    return (
      <Tabs
        label="Analysis"
        tabs={[
          { value: 'coach', label: 'Coach' },
          { value: 'moments', label: 'Critical moments' },
        ]}
        value={tab}
        onChange={setTab}
      >
        <p>Showing {tab}</p>
      </Tabs>
    )
  }

  test('arrow keys move between tabs and focus follows', () => {
    render(<Panel />)
    const coach = screen.getByRole('tab', { name: 'Coach' })
    expect(coach).toHaveAttribute('aria-selected', 'true')

    fireEvent.keyDown(coach, { key: 'ArrowRight' })

    const moments = screen.getByRole('tab', { name: 'Critical moments' })
    expect(moments).toHaveAttribute('aria-selected', 'true')
    expect(moments).toHaveFocus()
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Showing moments')
    fireEvent.keyDown(moments, { key: 'Home' })
    expect(coach).toHaveAttribute('aria-selected', 'true')
  })
})

describe('tooltip', () => {
  test('shows on focus, describes its element, and hides on Esc', () => {
    render(
      <Tooltip text="Disabled during an unsolved moment">
        <button type="button">Explain</button>
      </Tooltip>,
    )
    const button = screen.getByRole('button', { name: 'Explain' })
    const tip = screen.getByRole('tooltip', { hidden: true })
    expect(tip).not.toBeVisible()

    fireEvent.focus(button)
    expect(tip).toBeVisible()
    expect(button).toHaveAttribute('aria-describedby', tip.id)
    fireEvent.keyDown(button, { key: 'Escape' })
    expect(tip).not.toBeVisible()
  })
})

describe('modal', () => {
  function Host() {
    const [open, setOpen] = useState(false)
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Shortcuts
        </button>
        <Modal title="Keyboard shortcuts" open={open} onClose={() => setOpen(false)}>
          <p>Press ? any time.</p>
        </Modal>
      </>
    )
  }

  test('focus moves in, Esc closes, and focus returns', () => {
    render(<Host />)
    const opener = screen.getByRole('button', { name: 'Shortcuts' })
    opener.focus()

    fireEvent.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Keyboard shortcuts' })
    expect(dialog).toContainElement(document.activeElement as HTMLElement)

    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })
})

describe('toasts', () => {
  function Trigger() {
    const { show } = useToast()
    return (
      <button type="button" onClick={() => show("Couldn't reach the server.", 'error')}>
        Fail
      </button>
    )
  }

  test('an error toast is announced and goes away on its own or when dismissed', () => {
    vi.useFakeTimers()
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Fail' }))
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't reach the server.")
    act(() => vi.advanceTimersByTime(TOAST_MS.error))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Fail' }))
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    vi.useRealTimers()
  })
})

describe('step chips', () => {
  test('mark the current step and say which are done', () => {
    const onSelect = vi.fn()
    render(
      <StepChips
        label="Moments in this game"
        onSelect={onSelect}
        steps={[
          { key: 1, label: 'Moment 1', state: 'done' },
          { key: 2, label: 'Moment 2', state: 'current' },
          { key: 3, label: 'Moment 3', state: 'upcoming' },
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: 'Moment 2' })).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('button', { name: /^Moment 1\s*\(done\)$/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Moment 3' }))
    expect(onSelect).toHaveBeenCalledWith(3)
  })
})

describe('states', () => {
  test('an error offers a retry', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="The games couldn't be loaded." onRetry={onRetry} />)

    expect(screen.getByRole('alert')).toHaveTextContent("The games couldn't be loaded.")
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })

  test('an empty state says what to do next', () => {
    render(<EmptyState title="No games yet" action={<a href="/new">Analyze a game</a>} />)

    expect(screen.getByRole('heading', { name: 'No games yet' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analyze a game' })).toBeInTheDocument()
  })

  test('progress reports its value', () => {
    render(<ProgressBar label="Game 8 of 12" done={7} total={12} />)

    const bar = screen.getByRole('progressbar', { name: 'Game 8 of 12' })
    expect(bar).toHaveAttribute('aria-valuenow', '7')
    expect(bar).toHaveAttribute('aria-valuemax', '12')
  })

  test('chat bubbles say who is talking to screen readers', () => {
    render(<ChatBubble from="coach">Look at the knight.</ChatBubble>)

    expect(screen.getByText('Coach:', { exact: false })).toHaveClass('visually-hidden')
  })
})

describe('header', () => {
  test('marks the active page and offers the other theme', () => {
    const onToggleTheme = vi.fn()
    render(
      <MemoryRouter initialEntries={['/games/abc']}>
        <Header
          nav={[
            { to: '/games', label: 'Games', activeFor: (p) => p === '/games' },
            { to: '/games/abc', label: 'Analysis', activeFor: (p) => p.startsWith('/games/') },
          ]}
          pathname="/games/abc"
          playerName="Alex"
          theme="light"
          onToggleTheme={onToggleTheme}
        />
      </MemoryRouter>,
    )

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent('Analysis')
    expect(screen.getByText('Alex')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
    expect(onToggleTheme).toHaveBeenCalled()
  })
})
