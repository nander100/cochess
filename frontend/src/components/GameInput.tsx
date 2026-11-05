import { type FormEvent, useId, useState } from 'react'
import type { Color, CreateGameRequest } from '../api/types'
import { SegmentedToggle, type ToggleOption } from '../ui'

interface GameInputProps {
  disabled: boolean
  onSubmit: (request: CreateGameRequest) => void
}

const COLOR_HINT = 'Choose the color you played first.'
const COLORS: readonly ToggleOption<Color>[] = [
  { value: 'white', label: 'I played White' },
  { value: 'black', label: 'I played Black' },
]

/** One game to analyze. Rating and playstyle come from the player's profile (SPEC_V2 §4.3).
 * The color comes first and starts unselected: the PGN box and Analyze wait for it, so a game
 * is never analyzed from the wrong side (SPEC_V3 §4.6). */
export function GameInput({ disabled, onSubmit }: GameInputProps) {
  const id = useId()
  const [color, setColor] = useState<Color | null>(null)
  const [pgn, setPgn] = useState('')
  const [error, setError] = useState<string | null>(null)
  const needsColor = color === null

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (color === null) {
      setError(COLOR_HINT)
      return
    }
    if (pgn.trim() === '') {
      setError('Paste the game you want to analyze (PGN).')
      return
    }
    setError(null)
    onSubmit({ pgn, user_color: color })
  }

  return (
    <form className="game-input" onSubmit={handleSubmit} noValidate aria-label="Game to analyze">
      <SegmentedToggle
        legend="Which color did you play?"
        options={COLORS}
        value={color}
        onChange={(value) => {
          setColor(value)
          setError(null)
        }}
        disabled={disabled}
        describedBy={needsColor ? `${id}-hint` : undefined}
      />
      {needsColor && (
        <p id={`${id}-hint`} className="form-hint">
          {COLOR_HINT}
        </p>
      )}

      <label htmlFor={`${id}-pgn`}>
        Your game (PGN)
        <textarea
          id={`${id}-pgn`}
          className="pgn"
          rows={10}
          spellCheck={false}
          placeholder={'[Event "Live Chess"]\n…\n1. d4 d5 2. Bf4 …'}
          value={pgn}
          onChange={(e) => setPgn(e.target.value)}
          disabled={disabled || needsColor}
          required
        />
      </label>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <button type="submit" disabled={disabled || needsColor}>
        Analyze
      </button>
    </form>
  )
}
