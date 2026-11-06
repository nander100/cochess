import { type FormEvent, useId, useState } from 'react'
import type { Color, CreateGameRequest } from '../api/types'
import { useSettings, usernames } from '../settings/settingsContext'
import { Button, SegmentedToggle, type ToggleOption } from '../ui'
import './GameInput.css'

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
 * is never analyzed from the wrong side (SPEC_V3 §4.6). A player who has given their Chess.com
 * or Lichess username can leave it: the backend finds that name in the PGN. */
export function GameInput({ disabled, onSubmit }: GameInputProps) {
  const id = useId()
  const { settings } = useSettings()
  const names = usernames(settings)
  const [color, setColor] = useState<Color | null>(null)
  const [pgn, setPgn] = useState('')
  const [error, setError] = useState<string | null>(null)
  const needsColor = color === null && names.length === 0
  const hint = names.length > 0 ? `Or leave it: we'll find ${names.join(' or ')} in the game.` : COLOR_HINT

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (needsColor) {
      setError(COLOR_HINT)
      return
    }
    if (pgn.trim() === '') {
      setError('Paste the game you want to analyze (PGN).')
      return
    }
    setError(null)
    onSubmit(color === null ? { pgn } : { pgn, user_color: color })
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
        describedBy={color === null ? `${id}-hint` : undefined}
      />
      {color === null && (
        <p id={`${id}-hint`} className="game-input-hint">
          {hint}
        </p>
      )}
      <label className="game-input-label" htmlFor={`${id}-pgn`}>
        Paste your game (PGN)
      </label>
      <textarea
        id={`${id}-pgn`}
        className="ui-input ui-textarea ui-mono"
        rows={6}
        spellCheck={false}
        placeholder={'[Event "Rated Rapid game"]\n1. e4 e5 2. Nf3 Nc6 ...'}
        value={pgn}
        onChange={(e) => setPgn(e.target.value)}
        disabled={disabled || needsColor}
        required
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" className="game-input-submit" disabled={disabled || needsColor}>
        Analyze game
      </Button>
    </form>
  )
}
