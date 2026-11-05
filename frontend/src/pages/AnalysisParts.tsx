import { type ReactNode, useId, useState } from 'react'
import type { GameDetail, UserResult } from '../api/types'
import { ChevronLeftIcon, ChevronRightIcon, FirstIcon, FlipIcon, IconButton, LastIcon, Pill } from '../ui'
import { ChevronDownIcon } from '../ui/icons'
import './AnalysisParts.css'
import { gameDate } from './util'

const RESULT: Record<UserResult, string> = { win: 'Win', loss: 'Loss', draw: 'Draw' }

function userResult(detail: GameDetail): UserResult | null {
  const { result } = detail.info
  if (result === '1/2-1/2') return 'draw'
  if (result === '1-0') return detail.user_color === 'white' ? 'win' : 'loss'
  if (result === '0-1') return detail.user_color === 'black' ? 'win' : 'loss'
  return null
}

/** "You vs [Opponent]", the game's facts, and the player's accuracy (Analysis.dc.html). */
export function GameHeading({ detail }: { detail: GameDetail }) {
  const { info, accuracy } = detail
  const opponent = detail.user_color === 'white' ? info.black : info.white
  const result = userResult(detail)
  const facts = [
    detail.user_color === 'white' ? 'White' : 'Black',
    info.time_control,
    result ? RESULT[result] : info.result,
    gameDate(detail.played_at),
    info.opening,
  ].filter(Boolean)
  return (
    <header className="game-heading">
      <h1 className="game-title">You vs {opponent}</h1>
      <p className="game-facts">
        <span className="visually-hidden">
          {info.white} – {info.black} {info.result}.{' '}
        </span>
        {facts.join(' · ')} · you played {detail.user_color}
      </p>
      {accuracy?.user != null && <Pill tone="analyzed">Accuracy {accuracy.user}</Pill>}
    </header>
  )
}

interface BoardNavProps {
  disabled: boolean
  onFirst: () => void
  onBack: () => void
  onForward: () => void
  onLast: () => void
  onFlip: () => void
}

/** First, previous, next (primary), last, and Flip board under the board. */
export function BoardNav({ disabled, onFirst, onBack, onForward, onLast, onFlip }: BoardNavProps) {
  return (
    <div className="board-nav" role="group" aria-label="Move navigation">
      <IconButton label="Start of the game (Home)" icon={<FirstIcon size="small" />} onClick={onFirst} disabled={disabled} />
      <IconButton label="Previous move (←)" icon={<ChevronLeftIcon size="small" />} onClick={onBack} disabled={disabled} />
      <IconButton
        label="Next move (→)"
        variant="primary"
        icon={<ChevronRightIcon size="small" />}
        onClick={onForward}
        disabled={disabled}
      />
      <IconButton label="End of the line (End)" icon={<LastIcon size="small" />} onClick={onLast} disabled={disabled} />
      <button type="button" className="ui-button ui-button-outline board-flip" onClick={onFlip}>
        <FlipIcon size="small" />
        Flip board
      </button>
    </div>
  )
}

/** The moves, collapsed by default (the owner's choice: room for the coach), with a summary. */
export function MovesPanel({ count, children }: { count: number; children: ReactNode }) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <section className="moves-panel" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="moves-panel-title">
        <button type="button" aria-expanded={open} aria-controls={`${id}-list`} onClick={() => setOpen(!open)}>
          <span className="moves-panel-name">Moves</span>
          <span className="moves-panel-summary">
            {count} move{count === 1 ? '' : 's'} · {open ? 'Hide' : 'Show'}
          </span>
          <ChevronDownIcon size="small" className={open ? 'moves-panel-chevron open' : 'moves-panel-chevron'} />
        </button>
      </h2>
      <div id={`${id}-list`} hidden={!open}>
        {children}
      </div>
    </section>
  )
}
