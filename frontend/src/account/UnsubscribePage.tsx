import { Link, useSearchParams } from 'react-router'
import type { AccountApi, EmailGroup } from '../api/accountTypes'
import { useLoad } from '../owner/useLoad'
import { AccountLayout } from '../pages/AccountLayout'
import { Skeleton } from '../ui'

const WHAT: Record<EmailGroup, string> = {
  credits_balance: 'emails about running low on credits',
  credits_added: 'emails when credits are added to your account',
}

/** The one-click link from an optional email (SPEC_V4 §12.4): opening it turns that email off. No
 * login needed; the signed token in the link is the check. */
export function UnsubscribePage({ api }: { api: AccountApi }) {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const { load } = useLoad(() => api.unsubscribe(token), token)
  return (
    <AccountLayout>
      <div className="redeem-state">
        {load.kind === 'loading' && <Skeleton lines={2} label="Turning that email off…" />}
        {load.kind === 'ready' && (
          <>
            <span className="redeem-badge">Done</span>
            <h1 className="redeem-title">You won't get these emails any more.</h1>
            <p className="redeem-lead">
              We've turned off {WHAT[load.data.group]}. You can turn them back on from your profile.
            </p>
          </>
        )}
        {load.kind === 'error' && (
          <div role="alert">
            <h1 className="redeem-title">That link didn't work.</h1>
            <p className="redeem-lead">{load.message}</p>
          </div>
        )}
        <Link to="/profile">Go to your profile</Link>
      </div>
    </AccountLayout>
  )
}
