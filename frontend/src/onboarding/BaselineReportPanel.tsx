import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { BaselineReport } from '../api/types'
import { errorText, gameDate } from '../pages/util'

interface BaselineReportPanelProps {
  api: ApiClient
  onLoggedOut: () => void
}

/** The latest baseline report, viewable any time from the profile (SPEC_V2 §10.4). */
export function BaselineReportPanel({ api, onLoggedOut }: BaselineReportPanelProps) {
  const [report, setReport] = useState<BaselineReport | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.baselineReport().then(setReport, (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    })
  }, [api, onLoggedOut])

  return (
    <section className="panel synopsis" aria-label="Baseline report">
      <h2>Baseline report</h2>
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
      {report === undefined && !error && <p className="coach-writing">Loading…</p>}
      {report === null && (
        <p>
          No baseline report yet. <Link to="/onboarding">Add your 12 assessment games</Link> and your coach will
          write one.
        </p>
      )}
      {report && (
        <>
          <p className="report-date">Written {gameDate(report.created_at)}</p>
          <div className="synopsis-text">
            <Markdown>{report.text}</Markdown>
          </div>
        </>
      )}
    </section>
  )
}
