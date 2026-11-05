import { useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Color, GameDetail } from '../api/types'
import { errorText } from './util'

interface GameOptionsProps {
  detail: GameDetail
  api: ApiClient
  /** The game after a color change (it may need a few positions verified). */
  onColorChanged: (detail: GameDetail) => void
  onDeleted: () => void
  onLoggedOut: () => void
}

type Confirm = null | 'color' | 'delete'

const NAME: Record<Color, string> = { white: 'White', black: 'Black' }

/** Fix a game analyzed from the wrong side, or delete it (PLAN_V3 M1). Each action asks once
 * before it runs, saying what will be lost. */
export function GameOptions({ detail, api, onColorChanged, onDeleted, onLoggedOut }: GameOptionsProps) {
  const [confirm, setConfirm] = useState<Confirm>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const other: Color = detail.user_color === 'white' ? 'black' : 'white'

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      setConfirm(null)
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    } finally {
      setBusy(false)
    }
  }

  const switchColor = () => run(async () => onColorChanged(await api.changeColor(detail.id, other)))
  const remove = () =>
    run(async () => {
      await api.deleteGame(detail.id)
      onDeleted()
    })

  return (
    <div className="game-options" role="region" aria-label="Game options">
      {confirm === null && (
        <>
          <button type="button" className="secondary" onClick={() => setConfirm('color')}>
            I played {NAME[other]}
          </button>
          <button type="button" className="secondary" onClick={() => setConfirm('delete')}>
            Delete game
          </button>
        </>
      )}
      {confirm === 'color' && (
        <div role="alertdialog" aria-label="Change color" className="game-options-confirm">
          <p>
            Switch this game to {NAME[other]}? The coach's notes and your critical-moment progress
            for it will be cleared, and the analysis is redone for {NAME[other]}.
          </p>
          <button type="button" onClick={() => void switchColor()} disabled={busy}>
            Switch to {NAME[other]}
          </button>
          <button type="button" className="secondary" onClick={() => setConfirm(null)} disabled={busy}>
            Cancel
          </button>
        </div>
      )}
      {confirm === 'delete' && (
        <div role="alertdialog" aria-label="Delete game" className="game-options-confirm">
          <p>Delete this game and its analysis, coach notes and moments? This can't be undone.</p>
          <button type="button" className="danger" onClick={() => void remove()} disabled={busy}>
            Delete game
          </button>
          <button type="button" className="secondary" onClick={() => setConfirm(null)} disabled={busy}>
            Cancel
          </button>
        </div>
      )}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
