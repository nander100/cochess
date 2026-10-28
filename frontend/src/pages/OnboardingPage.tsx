import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router'
import { coachStep } from '../analysis/moments'
import type { PipelineDeps } from '../analysis/pipeline'
import { type QueueProgress, queueLabel, runOnboardingQueue } from '../analysis/queue'
import { isLoggedOut } from '../api/client'
import type { OnboardingStatus } from '../api/types'
import { ProgressBar } from '../components/ProgressBar'
import { CATEGORY_LABEL, SLOT_LABEL } from '../onboarding/labels'
import { PasteGames } from '../onboarding/PasteGames'
import { SlotChecklist } from '../onboarding/SlotChecklist'
import { errorText, gameDate } from './util'

interface OnboardingPageProps {
  deps: PipelineDeps
  onLoggedOut: () => void
}

/** The onboarding assessment (SPEC_V2 §10.3): 12 games → analysis → the baseline report. */
export function OnboardingPage({ deps, onLoggedOut }: OnboardingPageProps) {
  const { api } = deps
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [progress, setProgress] = useState<QueueProgress | null>(null)
  const [writing, setWriting] = useState(false)
  const [report, setReport] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const running = useRef(false)

  const fail = useCallback(
    (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    },
    [onLoggedOut],
  )

  // Analyze whatever is still waiting. The server keeps each game's status, so this picks up where
  // a closed tab stopped.
  const analyze = useCallback(async () => {
    if (running.current) return
    running.current = true
    setError(null)
    try {
      setStatus(await runOnboardingQueue(deps, setProgress))
    } catch (caught) {
      fail(caught)
      api.onboardingStatus().then(setStatus, () => undefined)
    } finally {
      running.current = false
      setProgress(null)
    }
  }, [api, deps, fail])

  const refresh = useCallback(
    () =>
      api.onboardingStatus().then((fresh) => {
        setStatus(fresh)
        if (fresh.games.some((game) => game.status !== 'analyzed')) void analyze()
      }, fail),
    [analyze, api, fail],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function writeReport() {
    setError(null)
    setWriting(true)
    try {
      const reply = await coachStep((onEvent) => api.streamBaselineReport(onEvent), () => {})
      setReport(reply.text)
      setStatus(await api.onboardingStatus())
    } catch (caught) {
      fail(caught)
    } finally {
      setWriting(false)
    }
  }

  if (status === null) {
    return error ? (
      <p className="run-error" role="alert">
        {error}
      </p>
    ) : (
      <p className="coach-writing">Loading…</p>
    )
  }

  const shownReport = report ?? status.report?.text ?? null
  const primary = status.primary_time_control
  const pending = status.games.length - status.analyzed

  return (
    <div className="onboarding">
      <section className="panel" aria-labelledby="onboarding-title">
        <h2 id="onboarding-title">Your baseline assessment</h2>
        <p>
          Add 12 of your {primary ? CATEGORY_LABEL[primary].toLowerCase() : ''} games: 3 wins and 3 losses with White,
          and the same with Black. The engine analyzes each one here in your browser (about 10 minutes in all), then
          your coach writes a report on where you stand. <Link to="/games">Skip for now</Link>: you can analyze single
          games any time.
        </p>
        <SlotChecklist slots={status.slots} />
      </section>

      {!status.complete && <PasteGames api={api} onAdded={() => void refresh()} onLoggedOut={onLoggedOut} />}

      {status.games.length > 0 && (
        <section className="panel" aria-label="Your onboarding games">
          <h2>
            Games ({status.analyzed} of {status.games.length} analyzed)
          </h2>
          {progress && (
            <ProgressBar
              label={queueLabel(progress)}
              {...(progress.status.phase === 'starting' ? { done: 0, total: 1 } : progress.status)}
            />
          )}
          {!progress && pending > 0 && (
            <button type="button" onClick={() => void analyze()}>
              Continue analysis ({pending} left)
            </button>
          )}
          <ol className="onboarding-games">
            {status.games.map((game) => (
              <li key={game.id}>
                <span className="slot-tag">{SLOT_LABEL[game.slot]}</span> vs {game.opponent},{' '}
                {gameDate(game.played_at)}
                {game.opening ? ` · ${game.opening}` : ''} ·{' '}
                {game.status === 'analyzed' ? <Link to={`/games/${game.id}`}>Open</Link> : 'waiting for analysis'}
              </li>
            ))}
          </ol>
        </section>
      )}

      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}

      {(status.report_ready || shownReport) && (
        <section className="panel synopsis" aria-label="Baseline report">
          <h2>Baseline report</h2>
          {shownReport ? (
            <div className="synopsis-text">
              <Markdown>{shownReport}</Markdown>
            </div>
          ) : (
            <button type="button" onClick={() => void writeReport()} disabled={writing}>
              Write my baseline report
            </button>
          )}
          {writing && <p className="coach-writing">Your coach is reading all 12 games…</p>}
        </section>
      )}
    </div>
  )
}
