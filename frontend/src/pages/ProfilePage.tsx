import { type FormEvent, useId, useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Profile, TimeControl } from '../api/types'
import { errorText } from './util'

// Profile rules from SPEC_V2 §4.3, mirrored from backend/app/api/schemas.py.
export const MIN_ELO = 100
export const MAX_ELO = 3000
export const MAX_PLAYSTYLE_CHARS = 500
export const MAX_NAME_CHARS = 60

const TIME_CONTROLS: { value: TimeControl; label: string }[] = [
  { value: 'bullet', label: 'Bullet (under 3 minutes)' },
  { value: 'blitz', label: 'Blitz (3–8 minutes)' },
  { value: 'rapid', label: 'Rapid (8–25 minutes)' },
  { value: 'classical', label: 'Classical (25 minutes or more)' },
]

interface ProfilePageProps {
  api: ApiClient
  profile: Profile
  onSaved: (profile: Profile) => void
  onLoggedOut: () => void
}

/** The player's profile (SPEC_V2 §4.3). Filled in on first login, editable any time. */
export function ProfilePage({ api, profile, onSaved, onLoggedOut }: ProfilePageProps) {
  const id = useId()
  const [name, setName] = useState(profile.name)
  const [elo, setElo] = useState(profile.elo === null ? '' : String(profile.elo))
  const [timeControl, setTimeControl] = useState<TimeControl | ''>(profile.time_control ?? '')
  const [playstyle, setPlaystyle] = useState(profile.playstyle ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const eloValue = Number(elo)
    if (name.trim() === '') return setError('Enter your name.')
    if (elo.trim() === '' || !Number.isInteger(eloValue) || eloValue < MIN_ELO || eloValue > MAX_ELO) {
      return setError(`Enter your rating as a whole number from ${MIN_ELO} to ${MAX_ELO}.`)
    }
    if (timeControl === '') return setError('Choose the time control you play most.')
    setError(null)
    setSaving(true)
    setSaved(false)
    try {
      const updated = await api.updateMe({
        name: name.trim(),
        elo: eloValue,
        time_control: timeControl,
        playstyle: playstyle.trim(),
      })
      setSaved(true)
      onSaved(updated)
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="profile-form" onSubmit={(e) => void handleSubmit(e)} noValidate aria-label="Your profile">
      <h2>Your profile</h2>
      {!profile.complete && (
        <p className="intro">Welcome! Tell your coach a little about your chess before you start.</p>
      )}
      <label htmlFor={`${id}-name`}>
        Name
        <input
          id={`${id}-name`}
          maxLength={MAX_NAME_CHARS}
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={saving}
          required
        />
      </label>
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
          disabled={saving}
          required
        />
      </label>
      <label htmlFor={`${id}-tc`}>
        Time control you play most
        <select
          id={`${id}-tc`}
          value={timeControl}
          onChange={(e) => setTimeControl(e.target.value as TimeControl | '')}
          disabled={saving}
          required
        >
          <option value="">Choose…</option>
          {TIME_CONTROLS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label htmlFor={`${id}-playstyle`}>
        How do you like to play? <span className="optional">(optional)</span>
        <textarea
          id={`${id}-playstyle`}
          rows={2}
          maxLength={MAX_PLAYSTYLE_CHARS}
          placeholder="e.g. aggressive, I like the London System"
          value={playstyle}
          onChange={(e) => setPlaystyle(e.target.value)}
          disabled={saving}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {saved && <p role="status">Saved.</p>}
      <button type="submit" disabled={saving}>
        {profile.complete ? 'Save' : 'Save and continue'}
      </button>
    </form>
  )
}
