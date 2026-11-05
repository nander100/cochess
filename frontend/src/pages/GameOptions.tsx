import { useState } from 'react'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { Color, GameDetail } from '../api/types'
import { Button, useToast } from '../ui'
import './GameOptions.css'
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
  const { show } = useToast()
  const other: Color = detail.user_color === 'white' ? 'black' : 'white'

  async function run(action: () => Promise<void>) {
    setBusy(true)
    try {
      await action()
      setConfirm(null)
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else show(errorText(caught), 'error')
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
          <Button variant="outline" onClick={() => setConfirm('color')}>
            I played {NAME[other]}
          </Button>
          <Button variant="outline" onClick={() => setConfirm('delete')}>
            Delete game
          </Button>
        </>
      )}
      {confirm === 'color' && (
        <div role="alertdialog" aria-label="Change color" className="game-options-confirm">
          <p>
            Switch this game to {NAME[other]}? The coach's notes and your critical-moment progress
            for it will be cleared, and the analysis is redone for {NAME[other]}.
          </p>
          <Button onClick={() => void switchColor()} disabled={busy}>
            Switch to {NAME[other]}
          </Button>
          <Button variant="outline" onClick={() => setConfirm(null)} disabled={busy}>
            Cancel
          </Button>
        </div>
      )}
      {confirm === 'delete' && (
        <div role="alertdialog" aria-label="Delete game" className="game-options-confirm">
          <p>Delete this game and its analysis, coach notes and moments? This can't be undone.</p>
          <Button variant="danger" onClick={() => void remove()} disabled={busy}>
            Delete game
          </Button>
          <Button variant="outline" onClick={() => setConfirm(null)} disabled={busy}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  )
}
