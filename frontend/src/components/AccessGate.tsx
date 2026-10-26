import { type FormEvent, useId, useState } from 'react'

interface AccessGateProps {
  error: string | null
  onUnlock: (code: string) => void
}

/** The v1 test gate: one shared access code (SPEC §4.2). */
export function AccessGate({ error, onUnlock }: AccessGateProps) {
  const id = useId()
  const [code, setCode] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (code.trim()) onUnlock(code.trim())
  }

  return (
    <form className="access-gate" onSubmit={handleSubmit} aria-label="Access gate">
      <p>CoChess is in private testing. Enter the access code you were given.</p>
      <label htmlFor={`${id}-code`}>
        Access code
        <input
          id={`${id}-code`}
          type="password"
          autoComplete="current-password"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          required
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" disabled={code.trim() === ''}>
        Continue
      </button>
    </form>
  )
}
