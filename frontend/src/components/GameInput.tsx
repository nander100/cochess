import { type FormEvent, useId, useState } from 'react'
import type { Color, CreateGameRequest } from '../api/types'

interface GameInputProps {
  disabled: boolean
  onSubmit: (request: CreateGameRequest) => void
}

/** One game to analyze. Rating and playstyle come from the player's profile (SPEC_V2 §4.3). */
export function GameInput({ disabled, onSubmit }: GameInputProps) {
  const id = useId()
  const [color, setColor] = useState<Color>('white')
  const [pgn, setPgn] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pgn.trim() === '') {
      setError('Paste the game you want to analyze (PGN).')
      return
    }
    setError(null)
    onSubmit({ pgn, user_color: color })
  }

  return (
    <form className="game-input" onSubmit={handleSubmit} noValidate aria-label="Game to analyze">
      <fieldset disabled={disabled}>
        <legend>You played</legend>
        {(['white', 'black'] as const).map((value) => (
          <label key={value} className="radio">
            <input
              type="radio"
              name={`${id}-color`}
              value={value}
              checked={color === value}
              onChange={() => setColor(value)}
            />
            {value === 'white' ? 'White' : 'Black'}
          </label>
        ))}
      </fieldset>

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
          disabled={disabled}
          required
        />
      </label>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <button type="submit" disabled={disabled}>
        Analyze
      </button>
    </form>
  )
}
