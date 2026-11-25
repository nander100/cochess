import { useState } from 'react'
import type { AccountApi } from '../api/accountTypes'
import { errorText, saveFile } from '../pages/util'
import { Button, Input, Modal, useToast } from '../ui'
import './account.css'

interface DataActionsProps {
  api: AccountApi
  name: string
  /** True for an account with a live subscription: deleting it cancels the subscription. */
  subscribed?: boolean
  /** Deleted: the session has ended. */
  onDeleted: () => void
  /** Saves the file; injected in tests. */
  save?: (blob: Blob, filename: string) => void
}

/** Download everything, or delete the account (SPEC_V4 §11). Deleting is confirmed by typing
 * the account's name. */
export function DataActions({ api, name, subscribed = false, onDeleted, save = saveFile }: DataActionsProps) {
  const toast = useToast()
  const [exporting, setExporting] = useState(false)
  const [confirming, setConfirming] = useState(false)

  async function exportData() {
    setExporting(true)
    try {
      const { blob, filename } = await api.exportData()
      save(blob, filename)
    } catch (error) {
      toast.show(errorText(error), 'error')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="data-actions">
      <Button variant="outline" disabled={exporting} onClick={() => void exportData()}>
        {exporting ? 'Preparing your download…' : 'Download my data'}
      </Button>
      <Button variant="danger" onClick={() => setConfirming(true)}>
        Delete my account
      </Button>
      {confirming && (
        <DeleteDialog
          api={api}
          name={name}
          subscribed={subscribed}
          onClose={() => setConfirming(false)}
          onDeleted={onDeleted}
        />
      )}
    </div>
  )
}

interface DeleteDialogProps {
  api: AccountApi
  name: string
  subscribed: boolean
  onClose: () => void
  onDeleted: () => void
}

function DeleteDialog({ api, name, subscribed, onClose, onDeleted }: DeleteDialogProps) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const matches = typed.trim().toLowerCase() === name.toLowerCase()

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await api.deleteAccount(typed.trim())
      onDeleted()
    } catch (failure) {
      setError(errorText(failure))
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title="Delete your account?"
      onClose={() => !busy && onClose()}
      actions={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" disabled={busy || !matches} onClick={() => void remove()}>
            {busy ? 'Deleting…' : 'Delete for good'}
          </Button>
        </>
      }
    >
      <p>
        Your games, chats, reports, credits and settings are deleted at once, and this can't be undone. Download
        your data first if you want to keep it.
      </p>
      {subscribed && <p>Your subscription is cancelled straight away and won't renew.</p>}
      <p>Records of payments and coaching costs are kept without your name, as financial records.</p>
      <Input
        label={`Type your name (${name}) to confirm`}
        value={typed}
        autoComplete="off"
        onChange={(event) => setTyped(event.target.value)}
      />
      {error && (
        <p className="data-error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  )
}
