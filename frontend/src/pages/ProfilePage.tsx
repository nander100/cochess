import { type FormEvent, useEffect, useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { BoardScheme, DetailLevel, PieceSet, Profile, TendencyReport, TimeControl, UserSettings } from '../api/types'
import { BaselineReportPanel } from '../onboarding/BaselineReportPanel'
import { useSettings } from '../settings/settingsContext'
import { ShortcutList } from '../shortcuts/ShortcutHelp'
import type { ThemePreference } from '../theme/theme'
import { Button, Card, Input, SegmentedToggle, Skeleton, Switch, Textarea, type ToggleOption } from '../ui'
import './ProfilePage.css'
import { errorText } from './util'

// Profile rules from SPEC_V2 §4.3, mirrored from backend/app/api/schemas.py.
export const MIN_ELO = 100
export const MAX_ELO = 3000
export const MAX_PLAYSTYLE_CHARS = 500
export const MAX_NAME_CHARS = 60

const TIME_CONTROLS: readonly ToggleOption<TimeControl>[] = [
  { value: 'bullet', label: 'Bullet' },
  { value: 'blitz', label: 'Blitz' },
  { value: 'rapid', label: 'Rapid' },
  { value: 'classical', label: 'Classical' },
]

const THEMES: readonly ToggleOption<ThemePreference>[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'Match system' },
]

const BOARD_SCHEMES: readonly ToggleOption<BoardScheme>[] = [
  { value: 'blue', label: 'Baby blue' },
  { value: 'pale', label: 'Pale blue' },
  { value: 'soft', label: 'Soft blue' },
]

const PIECE_SETS: readonly ToggleOption<PieceSet>[] = [
  { value: 'cburnett', label: 'Classic' },
  { value: 'merida', label: 'Merida' },
]

const DETAIL_LEVELS: readonly ToggleOption<UserSettings['coach_detail_level']>[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'plain', label: 'Plain' },
  { value: 'standard', label: 'Standard' },
  { value: 'technical', label: 'Technical' },
]

const DETAIL_HELP: Record<DetailLevel, string> = {
  plain: 'Plain: everyday words, no notation, evaluations in words.',
  standard: 'Standard: words first, notation when you hover a move, the number after the words.',
  technical: 'Technical: notation and numbers, concise.',
}

const TIME_CONTROL_NAME: Record<TimeControl, string> = { bullet: 'Bullet', blitz: 'Blitz', rapid: 'Rapid', classical: 'Classical' }

interface ProfilePageProps {
  api: ApiClient
  profile: Profile
  onSaved: (profile: Profile) => void
  onLoggedOut: () => void
}

/** The player's profile and settings (SPEC_V2 §4.3, SPEC_V3 §4.3; Profile.dc.html). Filled in on
 * first login, editable any time. */
export function ProfilePage({ api, profile, onSaved, onLoggedOut }: ProfilePageProps) {
  const [report, setReport] = useState<TendencyReport | null>(null)

  useEffect(() => {
    if (!profile.complete) return
    api.tendencies().then(setReport, (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
    })
  }, [api, profile.complete, onLoggedOut])

  return (
    <div className="profile-page">
      <ProfileHeading profile={profile} gamesAnalyzed={report?.games_analyzed ?? null} />
      <div className="profile-columns">
        <div className="profile-main">
          <AboutYou api={api} profile={profile} onSaved={onSaved} onLoggedOut={onLoggedOut} />
          <SettingsSection />
        </div>
        {profile.complete && (
          <aside className="profile-aside" aria-label="Your progress">
            <BaselineReportPanel api={api} onLoggedOut={onLoggedOut} />
            <Tendencies report={report} />
          </aside>
        )}
      </div>
    </div>
  )
}

function ProfileHeading({ profile, gamesAnalyzed }: { profile: Profile; gamesAnalyzed: number | null }) {
  const facts = [
    profile.elo !== null ? `Elo ${profile.elo}` : null,
    profile.time_control ? TIME_CONTROL_NAME[profile.time_control] : null,
    gamesAnalyzed !== null ? `${gamesAnalyzed} game${gamesAnalyzed === 1 ? '' : 's'} analyzed` : null,
  ].filter(Boolean)
  return (
    <div className="profile-heading">
      <span className="profile-avatar" aria-hidden="true">
        {profile.name.trim().charAt(0).toUpperCase() || '?'}
      </span>
      <div>
        <h1 className="profile-name">{profile.name}</h1>
        {facts.length > 0 && <p className="profile-facts">{facts.join(' · ')}</p>}
      </div>
    </div>
  )
}

interface AboutYouProps {
  api: ApiClient
  profile: Profile
  onSaved: (profile: Profile) => void
  onLoggedOut: () => void
}

function AboutYou({ api, profile, onSaved, onLoggedOut }: AboutYouProps) {
  const [name, setName] = useState(profile.name)
  const [elo, setElo] = useState(profile.elo === null ? '' : String(profile.elo))
  const [timeControl, setTimeControl] = useState<TimeControl | null>(profile.time_control)
  const [playstyle, setPlaystyle] = useState(profile.playstyle ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  function reset() {
    setName(profile.name)
    setElo(profile.elo === null ? '' : String(profile.elo))
    setTimeControl(profile.time_control)
    setPlaystyle(profile.playstyle ?? '')
    setError(null)
    setSaved(false)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const eloValue = Number(elo)
    if (name.trim() === '') return setError('Enter your name.')
    if (elo.trim() === '' || !Number.isInteger(eloValue) || eloValue < MIN_ELO || eloValue > MAX_ELO) {
      return setError(`Enter your rating as a whole number from ${MIN_ELO} to ${MAX_ELO}.`)
    }
    if (timeControl === null) return setError('Choose the time control you play most.')
    setError(null)
    setSaving(true)
    setSaved(false)
    try {
      const updated = await api.updateMe({ name: name.trim(), elo: eloValue, time_control: timeControl, playstyle: playstyle.trim() })
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
    <form className="ui-card profile-card" onSubmit={(e) => void handleSubmit(e)} noValidate aria-labelledby="profile-about">
      <h2 id="profile-about" className="profile-card-title">
        About you
      </h2>
      {!profile.complete && <p className="profile-intro">Welcome! Tell your coach a little about your chess before you start.</p>}
      <div className="profile-fields">
        <Input label="Display name" maxLength={MAX_NAME_CHARS} value={name} onChange={(e) => setName(e.target.value)} disabled={saving} required />
        <Input
          label="Elo rating"
          type="number"
          inputMode="numeric"
          min={MIN_ELO}
          max={MAX_ELO}
          value={elo}
          onChange={(e) => setElo(e.target.value)}
          disabled={saving}
          required
          help={`${MIN_ELO}–${MAX_ELO}. Your coach pitches explanations to this level.`}
        />
      </div>
      <SegmentedToggle legend="Main time control" options={TIME_CONTROLS} value={timeControl} onChange={setTimeControl} disabled={saving} />
      <div className="profile-playstyle">
        <Textarea
          label={
            <>
              How you like to play <span className="profile-optional">(optional)</span>
            </>
          }
          rows={4}
          maxLength={MAX_PLAYSTYLE_CHARS}
          placeholder="e.g. I like open positions and attacking the king, but I get nervous in endgames."
          value={playstyle}
          onChange={(e) => setPlaystyle(e.target.value)}
          disabled={saving}
        />
        <span className="profile-counter" aria-live="polite">
          {playstyle.length} / {MAX_PLAYSTYLE_CHARS}
        </span>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="profile-saved" role="status">
          Saved.
        </p>
      )}
      <div className="profile-actions">
        {profile.complete && (
          <Button variant="outline" onClick={reset} disabled={saving}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={saving}>
          {profile.complete ? 'Save changes' : 'Save and continue'}
        </Button>
      </div>
    </form>
  )
}

/** Settings (SPEC_V3 §4.3) as a section of the profile, styled like the design's Appearance block.
 * Changes apply at once and are saved for the player; there's nothing to submit. */
function SettingsSection() {
  const { settings, update } = useSettings()
  return (
    <Card as="section" className="profile-card" aria-labelledby="profile-settings">
      <h2 id="profile-settings" className="profile-card-title">
        Settings
      </h2>
      <SegmentedToggle legend="Appearance" options={THEMES} value={settings.theme} onChange={(theme) => update({ theme })} />
      <SegmentedToggle
        legend="Board colors"
        options={BOARD_SCHEMES}
        value={settings.board_scheme}
        onChange={(board_scheme) => update({ board_scheme })}
      />
      <SegmentedToggle legend="Pieces" options={PIECE_SETS} value={settings.piece_set} onChange={(piece_set) => update({ piece_set })} />
      <SegmentedToggle
        legend="Coach detail level"
        options={DETAIL_LEVELS}
        value={settings.coach_detail_level}
        onChange={(coach_detail_level) => update({ coach_detail_level })}
      />
      <p className="profile-help">
        {DETAIL_HELP[settings.effective_detail_level]}
        {settings.coach_detail_level === 'auto' && ' (Auto follows your rating.)'}
      </p>
      <label className="profile-range">
        <span>Line playback speed: one move every {settings.playback_seconds} s</span>
        <input
          type="range"
          min={0.75}
          max={3}
          step={0.25}
          value={settings.playback_seconds}
          onChange={(event) => update({ playback_seconds: Number(event.target.value) })}
        />
      </label>
      <div className="profile-switches">
        <Switch label="Sounds on move" checked={settings.sounds} onChange={(sounds) => update({ sounds })} />
        <Switch
          label="Show the engine panel by default"
          help="The live engine stays off during an unsolved critical moment."
          checked={settings.engine_panel}
          onChange={(engine_panel) => update({ engine_panel })}
        />
      </div>
      <section aria-labelledby="profile-shortcuts" className="profile-shortcuts">
        <h3 id="profile-shortcuts" className="profile-subtitle">
          Keyboard shortcuts
        </h3>
        <ShortcutList />
      </section>
    </Card>
  )
}

function Tendencies({ report }: { report: TendencyReport | null }) {
  const top = report?.tendencies.slice(0, 5) ?? []
  const max = Math.max(...top.map((t) => t.score), 0)
  return (
    <Card as="section" className="profile-side-card" aria-labelledby="profile-tendencies">
      <h2 id="profile-tendencies" className="profile-side-title">
        Your tendencies
      </h2>
      <p className="profile-side-note">Recent games count more than old ones.</p>
      {report === null && <Skeleton lines={3} label="Loading your tendencies…" />}
      {report !== null && top.length === 0 && (
        <p className="profile-side-note">Analyze a few games and the mistakes that keep coming up show here.</p>
      )}
      {top.length > 0 && (
        <ul className="profile-tendencies">
          {top.map((tendency) => (
            <li key={tendency.theme}>
              <div className="profile-tendency-row">
                <span className="profile-tendency-name">{tendency.label}</span>
                <span className="profile-side-note">
                  {tendency.games_seen} game{tendency.games_seen === 1 ? '' : 's'}
                </span>
              </div>
              <div className="profile-bar" aria-hidden="true">
                <span style={{ inlineSize: `${max > 0 ? Math.round((tendency.score / max) * 100) : 0}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {report?.provisional && top.length > 0 && (
        <p className="profile-side-note">Based on only a few games so far.</p>
      )}
    </Card>
  )
}
