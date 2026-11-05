import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { Link } from 'react-router'
import { coachStep } from '../analysis/moments'
import type { PipelineDeps } from '../analysis/pipeline'
import { type QueueProgress, queueLabel, runOnboardingQueue } from '../analysis/queue'
import { isLoggedOut } from '../api/client'
import type { OnboardingStatus } from '../api/types'
import { CATEGORY_LABEL, SLOT_LABEL } from '../onboarding/labels'
import { PasteGames } from '../onboarding/PasteGames'
import { SlotChecklist } from '../onboarding/SlotChecklist'
import { Button, Card, ErrorState, Eyebrow, FeatureCard, Pill, ProgressBar, Skeleton, TypingIndicator, useToast } from '../ui'
import './OnboardingPage.css'
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
  const [notice, setNotice] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null) // asking before removing this game
  const running = useRef(false)

  const { show } = useToast()
  // Before the page has loaded, an error replaces it (with a retry); after, actions that fail
  // report as toasts (SPEC_V3 §4.2). A ref, so `fail` (and the load effect) stay stable.
  const loaded = useRef(false)
  useEffect(() => {
    loaded.current = status !== null
  })
  const fail = useCallback(
    (caught: unknown) => {
      if (isLoggedOut(caught)) onLoggedOut()
      else if (loaded.current) show(errorText(caught), 'error')
      else setError(errorText(caught))
    },
    [onLoggedOut, show],
  )

  // Analyze whatever is still waiting. The server keeps each game's status, so this picks up where
  // a closed tab stopped.
  const analyze = useCallback(async () => {
    if (running.current) return
    running.current = true
    setError(null)
    try {
      setStatus(await runOnboardingQueue(deps, setProgress, setStatus))
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

  /** Take a game out of the assessment, freeing its slot (PLAN_V3 M1). */
  async function remove(gameId: string) {
    setError(null)
    try {
      await api.deleteGame(gameId)
      setRemoving(null)
      setNotice('Removed the game. Its slot is open again.')
      setStatus(await api.onboardingStatus())
    } catch (caught) {
      fail(caught)
    }
  }

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
      <ErrorState message={error} onRetry={() => void refresh()} />
    ) : (
      <Skeleton lines={4} label="Loading your assessment…" />
    )
  }

  const shownReport = report ?? status.report?.text ?? null
  const primary = status.primary_time_control
  const pending = status.games.length - status.analyzed
  const filled = status.slots.reduce((sum, slot) => sum + Math.min(slot.filled, slot.of), 0)
  const needed = status.slots.reduce((sum, slot) => sum + slot.of, 0)

  return (
    <div className="onboarding">
      <section className="onboarding-hero" aria-labelledby="onboarding-title">
        <div className="onboarding-hero-text">
          <Eyebrow>Assessment</Eyebrow>
          <h1 id="onboarding-title" className="onboarding-title">
            Twelve games, one honest picture of your play.
          </h1>
          <p className="onboarding-lead">
            Add 3 wins and 3 losses with each color, all in your main time control
            {primary ? ` (${CATEGORY_LABEL[primary]})` : ''}. The engine analyzes each one here in your browser (about 10
            minutes in all); then your coach writes a baseline report on where you stand.
          </p>
        </div>
        <Link to="/games" className="onboarding-skip">
          Skip for now
        </Link>
      </section>

      <section className="onboarding-slots" aria-labelledby="onboarding-slots">
        <div className="onboarding-section-head">
          <h2 id="onboarding-slots" className="onboarding-section-title">
            Your 12 slots
          </h2>
          <span className="onboarding-muted">
            {filled} of {needed} filled
          </span>
        </div>
        <SlotChecklist slots={status.slots} />
      </section>

      {!status.complete && (
        <PasteGames
          api={api}
          onAdded={(message) => {
            setNotice(message)
            void refresh()
          }}
          onLoggedOut={onLoggedOut}
        />
      )}
      {notice && (
        <p className="onboarding-notice" role="status">
          {notice}
        </p>
      )}

      {status.games.length > 0 && (
        <Card as="section" className="onboarding-progress" aria-label="Your onboarding games">
          <div className="onboarding-section-head">
            <h2 className="onboarding-card-title">
              Games ({status.analyzed} of {status.games.length} analyzed)
            </h2>
            {pending > 0 && <span className="onboarding-muted">Analyzing in your browser</span>}
          </div>
          {progress && (
            <ProgressBar
              label={queueLabel(progress)}
              {...(progress.status.phase === 'starting' ? { done: 0, total: 1 } : progress.status)}
            />
          )}
          {pending > 0 && (
            <p className="onboarding-muted">You can close this tab: the analysis picks up where it stopped.</p>
          )}
          {!progress && pending > 0 && (
            <Button className="onboarding-continue" onClick={() => void analyze()}>
              Continue analysis ({pending} left)
            </Button>
          )}
          <ol className="onboarding-games">
            {status.games.map((game) => (
              <li key={game.id}>
                <Pill tone="neutral">{SLOT_LABEL[game.slot]}</Pill>
                <span className="onboarding-game-text">
                  vs {game.opponent}, {gameDate(game.played_at)}
                  {game.opening ? ` · ${game.opening}` : ''}
                </span>
                {game.status === 'analyzed' ? (
                  <Link to={`/games/${game.id}`}>Open</Link>
                ) : (
                  <span className="onboarding-muted">waiting for analysis</span>
                )}
                {removing === game.id ? (
                  <span role="group" aria-label={`Remove the game vs ${game.opponent}?`} className="onboarding-confirm">
                    Remove this game?
                    <Button variant="danger" onClick={() => void remove(game.id)}>
                      Remove
                    </Button>
                    <Button variant="outline" onClick={() => setRemoving(null)}>
                      Keep
                    </Button>
                  </span>
                ) : (
                  <Button
                    variant="link"
                    disabled={progress !== null}
                    aria-label={`Remove the game vs ${game.opponent}`}
                    onClick={() => setRemoving(game.id)}
                  >
                    Remove
                  </Button>
                )}
              </li>
            ))}
          </ol>
        </Card>
      )}

      {error && <ErrorState message={error} />}

      <FeatureCard as="section" className="onboarding-report" aria-label="Baseline report">
        <div className="onboarding-report-text">
          <span className="ui-eyebrow">Baseline report</span>
          {shownReport ? (
            <div className="onboarding-report-body">
              <Markdown>{shownReport}</Markdown>
            </div>
          ) : (
            <>
              <h2 className="onboarding-report-title">
                {status.report_ready ? 'Ready to write' : 'Unlocks when all 12 games are analyzed'}
              </h2>
              <p>
                Your strengths, the top three things to work on with examples from your games, how your openings are
                going, and a 2–4 week focus plan.
              </p>
            </>
          )}
          {writing && <TypingIndicator label="Your coach is reading all 12 games…" />}
        </div>
        {!shownReport &&
          (status.report_ready ? (
            <Button className="onboarding-write" onClick={() => void writeReport()} disabled={writing}>
              Write my baseline report
            </Button>
          ) : (
            <Button variant="outline" className="onboarding-locked" disabled>
              Generate report · {status.analyzed}/{needed}
            </Button>
          ))}
      </FeatureCard>
    </div>
  )
}
