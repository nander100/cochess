import { type FormEvent, useId, useState } from 'react'
import type { Color, CreateGameRequest } from '../api/types'

// Input rules from SPEC §3, mirrored from backend/app/api/schemas.py.
export const MIN_ELO = 100
export const MAX_ELO = 3000
export const MAX_PLAYSTYLE_CHARS = 500

interface GameInputProps {
  disabled: boolean
  onSubmit: (request: CreateGameRequest) => void
}

export function GameInput({ disabled, onSubmit }: GameInputProps) {
  const id = useId()
  const [elo, setElo] = useState('')
  const [color, setColor] = useState<Color>('white')
  const [playstyle, setPlaystyle] = useState('')
  const [pgn, setPgn] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const eloValue = Number(elo)
    if (elo.trim() === '' || !Number.isInteger(eloValue) || eloValue < MIN_ELO || eloValue > MAX_ELO) {
      setError(`Enter your rating as a whole number from ${MIN_ELO} to ${MAX_ELO}.`)
      return
    }
    if (pgn.trim() === '') {
      setError('Paste the game you want to analyze (PGN).')
      return
    }
    setError(null)
    onSubmit({ pgn, user_color: color, elo: eloValue, playstyle: playstyle.trim() || null })
  }

  return (
    <form className="game-input" onSubmit={handleSubmit} noValidate aria-label="Game to analyze">
      <div className="profile">
        <label htmlFor={`${id}-elo`}>
          Your rating (Elo)
          <input
            id={`${id}-elo`}
            type="number"
            inputMode="numeric"
            min={MIN_ELO}
            max={MAX_ELO}
            value={elo}
            onChange={(e) => setElo(e.target.value)}
            disabled={disabled}
            required
          />
        </label>

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
      </div>

      <label htmlFor={`${id}-playstyle`}>
        How do you like to play? <span className="optional">(optional)</span>
        <textarea
          id={`${id}-playstyle`}
          rows={2}
          maxLength={MAX_PLAYSTYLE_CHARS}
          placeholder="e.g. aggressive, I like the London System"
          value={playstyle}
          onChange={(e) => setPlaystyle(e.target.value)}
          disabled={disabled}
        />
      </label>

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
