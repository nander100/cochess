import Markdown from 'react-markdown'
import { Link } from 'react-router'
import type { AccountApi, LegalKind } from '../api/accountTypes'
import { useLoad } from '../owner/useLoad'
import { AccountLayout } from '../pages/AccountLayout'
import { ErrorState, Skeleton } from '../ui'
import './account.css'

/** /terms and /privacy (SPEC_V4 §11): public, the owner's text from the server (no raw HTML). */
export function LegalDocument({ api, kind }: { api: AccountApi; kind: LegalKind }) {
  const { load, reload } = useLoad(() => api.legal(kind), kind)
  return (
    <AccountLayout>
      <article className="legal-document">
        {load.kind === 'loading' && <Skeleton lines={8} label="Loading…" />}
        {load.kind === 'error' && <ErrorState message={load.message} onRetry={reload} />}
        {load.kind === 'ready' && (
          <>
            <Markdown skipHtml>{load.data.markdown}</Markdown>
            <p className="legal-version">Version {load.data.version}</p>
          </>
        )}
        <p>
          <Link to="/">Back to CoChess</Link>
        </p>
      </article>
    </AccountLayout>
  )
}
