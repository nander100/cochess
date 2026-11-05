import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { BaselineReport } from '../api/types'
import { errorText, gameDate } from '../pages/util'
import { Button, ErrorState, FeatureCard, Modal, Skeleton } from '../ui'
import './BaselineReportPanel.css'

interface BaselineReportPanelProps {
  api: ApiClient
  onLoggedOut: () => void
}

/** The latest baseline report, viewable any time from the profile (SPEC_V2 §10.4): a feature card
 * with its opening line, and the whole report in a dialog. */
export function BaselineReportPanel({ api, onLoggedOut }: BaselineReportPanelProps) {
  const [report, setReport] = useState<BaselineReport | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    api.baselineReport().then(setReport, (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    })
  }, [api, onLoggedOut])

  return (
    <FeatureCard as="section" className="baseline-card" aria-label="Baseline report">
      <p className="ui-eyebrow">Baseline report</p>
      {error && <ErrorState message={error} />}
      {report === undefined && !error && <Skeleton lines={2} label="Loading your baseline report…" />}
      {report === null && (
        <>
          <h2 className="baseline-title">Not written yet</h2>
          <p>
            <Link to="/onboarding">Add your 12 assessment games</Link> and your coach will write one.
          </p>
        </>
      )}
      {report && (
        <>
          <h2 className="baseline-title">Written {gameDate(report.created_at)} from your 12 games</h2>
          <p>{openingLine(report.text)}</p>
          <Button className="baseline-read" onClick={() => setOpen(true)}>
            Read the report
          </Button>
          <Modal title="Your baseline report" open={open} onClose={() => setOpen(false)}>
            <div className="baseline-text">
              <Markdown>{report.text}</Markdown>
            </div>
          </Modal>
        </>
      )}
    </FeatureCard>
  )
}

/** The report's first sentence of prose, without markdown headings or emphasis. */
function openingLine(text: string): string {
  const prose = text
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line !== '' && !line.startsWith('#'))
  const plain = (prose ?? '').replace(/[*_`>#]/g, '').replace(/^- /, '')
  const sentence = plain.match(/^.*?[.!?](\s|$)/)?.[0] ?? plain
  return sentence.trim()
}
