import { useState } from 'react'
import type { AccountApi, EmailGroup, EmailPreferences } from '../api/accountTypes'
import { useLoad } from '../owner/useLoad'
import { errorText } from '../pages/util'
import { Card, ErrorState, Skeleton, Switch, useToast } from '../ui'

const LABELS: Record<EmailGroup, { label: string; help: string }> = {
  credits_balance: { label: 'Low on credits', help: 'When you are running low or have run out.' },
  credits_added: { label: 'Credits added', help: 'When credits are added to your account for you.' },
}

/** Profile → Email (SPEC_V4 §12.4): the account emails a player can turn off. The others (the
 * waitlist, access, terms and deletion) always go out. */
export function EmailCard({ api, email }: { api: AccountApi; email: string | null }) {
  const toast = useToast()
  const { load, reload, replace } = useLoad(() => api.emailPreferences(), 'email')
  const [saving, setSaving] = useState<EmailGroup | null>(null)

  async function change(group: EmailGroup, on: boolean) {
    setSaving(group)
    try {
      const update: Partial<EmailPreferences> = { [group]: on }
      replace(await api.updateEmailPreferences(update))
    } catch (error) {
      toast.show(errorText(error), 'error')
    } finally {
      setSaving(null)
    }
  }

  return (
    <Card as="section" className="profile-card" aria-labelledby="profile-email">
      <h2 id="profile-email" className="profile-card-title">
        Email
      </h2>
      <p className="profile-intro">
        {email ? `Account emails go to ${email}.` : 'Connect Google to get account emails.'} We never send
        newsletters or promotions.
      </p>
      {load.kind === 'loading' && <Skeleton lines={2} label="Loading your email settings…" />}
      {load.kind === 'error' && <ErrorState message={load.message} onRetry={reload} />}
      {load.kind === 'ready' &&
        (Object.keys(LABELS) as EmailGroup[]).map((group) => (
          <Switch
            key={group}
            label={LABELS[group].label}
            help={LABELS[group].help}
            checked={load.data[group]}
            disabled={saving !== null}
            onChange={(on) => void change(group, on)}
          />
        ))}
    </Card>
  )
}
