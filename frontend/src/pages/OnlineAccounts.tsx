import { type FormEvent, useState } from 'react'
import { useSettings } from '../settings/settingsContext'
import { Button, Card, Input } from '../ui'

const USERNAME = /^[A-Za-z0-9_-]*$/
const MAX_USERNAME = 50
const BAD_NAME = 'Use only letters, numbers, "_" and "-".'

/** The player's Chess.com and Lichess usernames (owner decision, 2026-11-06): with one set, the
 * site finds the player's color in each pasted game from the PGN's player names. Remount it
 * (via `key`) once settings load, so the fields start from the saved names. */
export function OnlineAccounts() {
  const { settings, update } = useSettings()
  const [chesscom, setChesscom] = useState(settings.chesscom_username)
  const [lichess, setLichess] = useState(settings.lichess_username)
  const [saved, setSaved] = useState(false)
  const chesscomError = USERNAME.test(chesscom.trim()) ? undefined : BAD_NAME
  const lichessError = USERNAME.test(lichess.trim()) ? undefined : BAD_NAME
  const unchanged = chesscom.trim() === settings.chesscom_username && lichess.trim() === settings.lichess_username

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (chesscomError || lichessError) return
    update({ chesscom_username: chesscom.trim(), lichess_username: lichess.trim() })
    setSaved(true)
  }

  return (
    <Card as="section" className="profile-card" aria-labelledby="profile-accounts">
      <h2 id="profile-accounts" className="profile-card-title">
        Your online accounts
      </h2>
      <p className="profile-intro">
        Add the usernames you play under. When you paste games, we find your name in each one and fill in the color
        you played, so you don't have to.
      </p>
      <form onSubmit={handleSubmit} noValidate aria-label="Your online accounts" className="profile-accounts">
        <div className="profile-fields">
          <Input
            label="Chess.com username"
            maxLength={MAX_USERNAME}
            autoComplete="off"
            spellCheck={false}
            value={chesscom}
            error={chesscomError}
            onChange={(event) => {
              setChesscom(event.target.value)
              setSaved(false)
            }}
          />
          <Input
            label="Lichess username"
            maxLength={MAX_USERNAME}
            autoComplete="off"
            spellCheck={false}
            value={lichess}
            error={lichessError}
            onChange={(event) => {
              setLichess(event.target.value)
              setSaved(false)
            }}
          />
        </div>
        <div className="profile-actions">
          <Button type="submit" disabled={unchanged || Boolean(chesscomError || lichessError)}>
            Save usernames
          </Button>
          {saved && unchanged && (
            <span className="profile-saved" role="status">
              Saved
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}
