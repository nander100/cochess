import { type ReactNode, useState } from 'react'
import type { OwnerApi, PlayerDetail, SuspendRequest } from '../api/ownerTypes'
import { errorText } from '../pages/util'
import { Button, Input, Modal, SegmentedToggle, Textarea, useToast } from '../ui'

type Dialog = 'accept' | 'revoke' | 'restore' | 'credits' | 'metering' | null
/** Subscription states that still bill (backend LIVE). */
const BILLING = new Set(['active', 'trialing', 'past_due', 'incomplete'])
const MAX_CREDITS = 10_000
const MAX_NOTE = 200
const MAX_REASON = 500

interface PlayerActionsProps {
  api: OwnerApi
  detail: PlayerDetail
  onChanged: (detail: PlayerDetail) => void
}

/** The owner's actions on one player (SPEC_V4 §10.2), each confirmed in a dialog and written to
 * the audit log by the server. Which ones show depends on the player's status. */
export function PlayerActions({ api, detail, onChanged }: PlayerActionsProps) {
  const toast = useToast()
  const [dialog, setDialog] = useState<Dialog>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { row } = detail

  function open(which: Dialog) {
    setError(null)
    setDialog(which)
  }

  async function run(action: () => Promise<PlayerDetail>, done: string) {
    setBusy(true)
    setError(null)
    try {
      onChanged(await action())
      setDialog(null)
      toast.show(done, 'info')
    } catch (failure) {
      setError(errorText(failure)) // a refusal stays in the dialog, next to what was typed
    } finally {
      setBusy(false)
    }
  }

  const shared = { busy, error, onClose: () => !busy && setDialog(null) }
  return (
    <div className="owner-actions" role="group" aria-label="Actions">
      {row.status === 'waitlisted' && <Button onClick={() => open('accept')}>Accept</Button>}
      {row.status === 'suspended' && <Button onClick={() => open('restore')}>Restore access</Button>}
      <Button variant="outline" onClick={() => open('credits')}>
        Add or remove credits
      </Button>
      <Button variant="outline" onClick={() => open('metering')}>
        {row.unmetered ? 'Charge for coaching again' : 'Never charge'}
      </Button>
      {row.status !== 'suspended' && (
        <Button variant="danger" onClick={() => open('revoke')}>
          Revoke access
        </Button>
      )}

      <Confirm
        {...shared}
        open={dialog === 'accept'}
        title={`Accept ${row.name}?`}
        confirm="Accept"
        onConfirm={() => void run(() => api.accept(row.id), `Accepted ${row.name}.`)}
      >
        <p>They can sign in straight away, with the free trial credits, and get an acceptance email.</p>
      </Confirm>
      <Confirm
        {...shared}
        open={dialog === 'restore'}
        title={`Restore ${row.name}'s access?`}
        confirm="Restore access"
        onConfirm={() => void run(() => api.restore(row.id), `Restored ${row.name}.`)}
      >
        <p>
          {detail.admitted_at
            ? 'They can sign in again and get an email saying so.'
            : 'They were never accepted, so they go back on the waitlist (no email).'}
        </p>
      </Confirm>
      <Confirm
        {...shared}
        open={dialog === 'metering'}
        title={row.unmetered ? `Charge ${row.name} again?` : `Never charge ${row.name}?`}
        confirm={row.unmetered ? 'Charge again' : 'Never charge'}
        onConfirm={() =>
          void run(
            () => api.setMetering(row.id, !row.unmetered),
            row.unmetered ? `${row.name} is charged for coaching again.` : `${row.name} is never charged.`,
          )
        }
      >
        <p>
          {row.unmetered
            ? 'Their coaching will use their credits again, and stop at zero.'
            : 'Their coaching won’t use credits. Its API cost still shows here.'}
        </p>
      </Confirm>
      {dialog === 'revoke' && (
        <RevokeDialog
          {...shared}
          detail={detail}
          onConfirm={(body) => void run(() => api.suspend(row.id, body), `Revoked ${row.name}'s access.`)}
        />
      )}
      {dialog === 'credits' && (
        <CreditsDialog
          {...shared}
          name={row.name}
          onConfirm={(amount, note, emailNote) => {
            const verb = amount > 0 ? 'Added' : 'Removed'
            void run(() => api.changeCredits(row.id, amount, note, emailNote), `${verb} ${Math.abs(amount)} credits.`)
          }}
        />
      )}
    </div>
  )
}

interface DialogBase {
  busy: boolean
  error: string | null
  onClose: () => void
}

function DialogError({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p className="owner-dialog-error" role="alert">
      {error}
    </p>
  )
}

function Confirm({
  open,
  title,
  confirm,
  onConfirm,
  busy,
  error,
  onClose,
  children,
}: DialogBase & { open: boolean; title: string; confirm: string; onConfirm: () => void; children: ReactNode }) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={onConfirm}>
            {busy ? 'Working…' : confirm}
          </Button>
        </>
      }
    >
      {children}
      <DialogError error={error} />
    </Modal>
  )
}

function RevokeDialog({
  detail,
  onConfirm,
  busy,
  error,
  onClose,
}: DialogBase & { detail: PlayerDetail; onConfirm: (body: SuspendRequest) => void }) {
  const [reason, setReason] = useState('')
  const [tell, setTell] = useState(false)
  const [cancel, setCancel] = useState(false)
  const billing = detail.subscription_status !== null && BILLING.has(detail.subscription_status)
  const ready = reason.trim().length > 0
  const body = { reason: reason.trim(), tell_reason: tell, cancel_subscription: billing && cancel }
  return (
    <Modal
      open
      title={`Revoke ${detail.row.name}'s access?`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" disabled={busy || !ready} onClick={() => onConfirm(body)}>
            {busy ? 'Revoking…' : body.cancel_subscription ? 'Revoke and cancel' : 'Revoke access'}
          </Button>
        </>
      }
    >
      <p>They’re signed out everywhere and can only download or delete their data until you restore them.</p>
      <Textarea
        label="Reason (kept in the audit log)"
        value={reason}
        maxLength={MAX_REASON}
        rows={3}
        onChange={(e) => setReason(e.target.value)}
      />
      <label className="owner-check">
        <input type="checkbox" checked={tell} onChange={(e) => setTell(e.target.checked)} />
        Include the reason in the email to them
      </label>
      {billing && (
        <div className="owner-warning">
          <p>
            <strong>They have a subscription</strong> ({detail.subscription_status}). Revoking access doesn’t
            stop Stripe charging them.
          </p>
          <label className="owner-check">
            <input type="checkbox" checked={cancel} onChange={(e) => setCancel(e.target.checked)} />
            Also cancel their subscription in Stripe now
          </label>
        </div>
      )}
      <DialogError error={error} />
    </Modal>
  )
}

function CreditsDialog({
  name,
  onConfirm,
  busy,
  error,
  onClose,
}: DialogBase & { name: string; onConfirm: (credits: number, note: string, emailNote: boolean) => void }) {
  const [direction, setDirection] = useState<'add' | 'remove'>('add')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [emailNote, setEmailNote] = useState(false)
  const value = Number(amount)
  const valid = amount !== '' && Number.isFinite(value) && value > 0 && value <= MAX_CREDITS
  const ready = valid && note.trim().length > 0
  const verb = direction === 'add' ? 'Add' : 'Remove'
  return (
    <Modal
      open
      title={`Credits for ${name}`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={busy || !ready}
            onClick={() => onConfirm(direction === 'add' ? value : -value, note.trim(), direction === 'add' && emailNote)}
          >
            {busy ? 'Saving…' : valid ? `${verb} ${value} credits` : `${verb} credits`}
          </Button>
        </>
      }
    >
      <SegmentedToggle
        legend="Add or remove"
        hideLegend
        options={[
          { value: 'add', label: 'Add' },
          { value: 'remove', label: 'Remove' },
        ]}
        value={direction}
        onChange={setDirection}
      />
      <Input
        label="Credits"
        type="number"
        inputMode="decimal"
        min={0.1}
        max={MAX_CREDITS}
        step={0.1}
        value={amount}
        error={amount !== '' && !valid ? `Between 0.1 and ${MAX_CREDITS.toLocaleString()}.` : null}
        onChange={(e) => setAmount(e.target.value)}
      />
      <Input
        label="Note (required; the player sees it in their credit history)"
        value={note}
        maxLength={MAX_NOTE}
        onChange={(e) => setNote(e.target.value)}
      />
      {direction === 'add' && (
        <label className="owner-check">
          <input type="checkbox" checked={emailNote} onChange={(e) => setEmailNote(e.target.checked)} />
          Include the note in the email to them
        </label>
      )}
      <p className="owner-quiet">
        These are lasting credits: they don’t expire. Added credits are emailed to the player, unless they turned
        that email off.
      </p>
      <DialogError error={error} />
    </Modal>
  )
}
