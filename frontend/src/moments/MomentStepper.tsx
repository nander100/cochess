import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import {
  type BeforeSearches,
  type MomentDeps,
  type MomentProgress,
  type MomentReply,
  coachStep,
  sanOf,
  showMe,
  tryMove,
} from '../analysis/moments'
import { isLoggedOut } from '../api/client'
import type { MomentInfo, MomentMessage } from '../api/types'
import { errorText } from '../pages/util'
import { isUnsolved, numbered } from './moment'

const MAX_TEXT_CHARS = 2000 // mirrors the backend's limit on reasoning and questions

const PROGRESS_LABEL: Record<MomentProgress, string> = {
  checking: 'The engine is checking…',
  writing: 'Coach is writing…',
}

const GRADE_LABEL: Record<string, string> = {
  best: 'Best move!',
  good: 'Good move!',
  inaccuracy: 'Inaccuracy',
  mistake: 'Mistake',
  blunder: 'Blunder',
}

interface MomentStepperProps {
  gameId: string
  moments: readonly MomentInfo[]
  /** The index of the moment on screen. */
  current: number
  onSelect: (index: number) => void
  /** The position before the moment's move (from the game tree). */
  fen: string
  /** The move the player has played on the board for this moment, as UCI, not yet sent. */
  candidate: string | null
  onTakeBack: () => void
  deps: MomentDeps
  searches: BeforeSearches
  /** Fresh moments from the server after each step (the server is the record of progress). */
  onUpdated: (moments: MomentInfo[]) => void
  onLoggedOut: () => void
}

/** The critical-moment exercise (SPEC_V2 §8.2): intro → attempts → feedback → reveal → next. */
export function MomentStepper(props: MomentStepperProps) {
  const { gameId, moments, current, onSelect, fen, candidate, onTakeBack, deps, searches, onUpdated, onLoggedOut } =
    props
  const id = useId()
  const moment = moments.find((m) => m.index === current) ?? moments[0]
  const [progress, setProgress] = useState<MomentProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  // What was said in this step, until the server's record replaces it.
  const [pending, setPending] = useState<MomentMessage[]>([])
  const [reasoning, setReasoning] = useState('')
  const [question, setQuestion] = useState('')
  const [lastGrade, setLastGrade] = useState<string | null>(null)
  const busy = progress !== null
  const last = moments[moments.length - 1]
  const wrapUp = last.messages.find((m) => m.kind === 'wrap_up')

  async function step(said: string | null, run: () => Promise<MomentReply>) {
    setError(null)
    setLastGrade(null)
    setPending(said ? [{ role: 'player', text: said, kind: 'pending' }] : [])
    try {
      const reply = await run()
      setLastGrade(reply.grade)
      setPending((previous) => [...previous, { role: 'coach', text: reply.text, kind: 'pending' }])
      const fresh = await deps.api.getGame(gameId)
      setPending([])
      onUpdated(fresh.moments)
    } catch (caught) {
      if (isLoggedOut(caught)) onLoggedOut()
      else setError(errorText(caught))
    } finally {
      setProgress(null)
    }
  }

  function select(index: number) {
    setPending([])
    setLastGrade(null)
    setError(null)
    onSelect(index)
  }

  const start = () =>
    void step(null, () => coachStep((onEvent) => deps.api.momentStart(gameId, moment.index, onEvent), setProgress))

  function check(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!candidate || busy) return
    const why = reasoning.trim()
    const san = sanOf(fen, candidate)
    void step(why ? `${san}: ${why}` : san, async () => {
      try {
        const reply = await tryMove(deps, searches, gameId, moment.index, fen, candidate, why, setProgress)
        setReasoning('')
        return reply
      } finally {
        onTakeBack()
      }
    })
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    setQuestion('')
    void step(text, () =>
      coachStep((onEvent) => deps.api.momentAsk(gameId, moment.index, text, onEvent), setProgress),
    )
  }

  function reveal() {
    onTakeBack()
    void step('Show me.', () => showMe(deps, searches, gameId, moment.index, fen, setProgress))
  }

  const finish = () => void step(null, () => coachStep((onEvent) => deps.api.momentWrapUp(gameId, onEvent), setProgress))

  const messages = [...moment.messages.filter((m) => m.kind !== 'wrap_up'), ...pending]
  const log = useRef<HTMLUListElement>(null)
  // Keep the newest message in view: the log scrolls once the exercise gets long.
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [messages.length, moment.index])
  const position = moments.indexOf(moment)
  const next = moments[position + 1]
  const open = moment.state === 'intro' || moment.state === 'attempt'

  return (
    <section className="moments" aria-label="Critical moments">
      <ol className="moment-list" aria-label="Moments in this game">
        {moments.map((m) => (
          <li key={m.index}>
            <button
              type="button"
              className={`moment-chip ${m.state}`}
              aria-current={m.index === moment.index ? 'step' : undefined}
              disabled={busy}
              onClick={() => select(m.index)}
            >
              {numbered(m, m.san)}
              <span className="visually-hidden"> ({stateText(m)})</span>
            </button>
          </li>
        ))}
      </ol>

      <h2>
        Moment {position + 1} of {moments.length}
      </h2>
      <p className="moment-summary">
        You played <strong>{numbered(moment, moment.san)}</strong> ({moment.label.replace('_', ' ')}):{' '}
        {moment.eval_before} → {moment.eval_after}
      </p>

      {messages.length > 0 && (
        <ul ref={log} className="chat-log" aria-live="polite">
          {messages.map((message, i) => (
            <li key={i} className={`chat-message ${message.role}`}>
              <span className="chat-author">{message.role === 'coach' ? 'Coach' : 'You'}</span>
              <Markdown>{message.text}</Markdown>
            </li>
          ))}
        </ul>
      )}
      {lastGrade && !busy && <p className={`moment-grade ${lastGrade}`}>{GRADE_LABEL[lastGrade] ?? lastGrade}</p>}
      {progress && <p className="coach-writing">{PROGRESS_LABEL[progress]}</p>}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}

      {moment.state === 'new' && (
        <button type="button" onClick={start} disabled={busy}>
          Start this moment
        </button>
      )}

      {open && (
        <div className="moment-controls">
          {candidate ? (
            <form className="moment-attempt" onSubmit={check}>
              <p>
                Your move: <strong>{numbered(moment, sanOf(fen, candidate))}</strong>
              </p>
              <label htmlFor={`${id}-why`}>Why this move? (optional)</label>
              <textarea
                id={`${id}-why`}
                value={reasoning}
                maxLength={MAX_TEXT_CHARS}
                rows={2}
                onChange={(event) => setReasoning(event.target.value)}
                disabled={busy}
              />
              <div className="moment-actions">
                <button type="submit" disabled={busy}>
                  Check my move
                </button>
                <button type="button" className="secondary" onClick={onTakeBack} disabled={busy}>
                  Take back
                </button>
              </div>
            </form>
          ) : (
            <p className="chat-hint">{busy ? 'Waiting for the coach…' : 'Play your move on the board.'}</p>
          )}
          <form className="chat-form" onSubmit={ask}>
            <label className="visually-hidden" htmlFor={`${id}-ask`}>
              Ask the coach about this moment
            </label>
            <input
              id={`${id}-ask`}
              value={question}
              maxLength={MAX_TEXT_CHARS}
              placeholder="Ask for a hint…"
              onChange={(event) => setQuestion(event.target.value)}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !question.trim()}>
              Ask
            </button>
          </form>
          <button type="button" className="secondary" onClick={reveal} disabled={busy}>
            Show me
          </button>
        </div>
      )}

      {!isUnsolved(moment) && (
        <div className="moment-controls">
          {moment.best_san && (
            <p className="moment-best">
              The engine's move: <strong>{numbered(moment, moment.best_san)}</strong>. Your tries and the engine's
              move are on the board as variations.
            </p>
          )}
          {next ? (
            <button type="button" onClick={() => select(next.index)} disabled={busy}>
              Next moment
            </button>
          ) : (
            moments.every((m) => !isUnsolved(m)) &&
            !wrapUp && (
              <button type="button" onClick={finish} disabled={busy}>
                Wrap up
              </button>
            )
          )}
        </div>
      )}
      {wrapUp && moment.index === last.index && (
        <div className="chat-message coach moment-wrap-up">
          <span className="chat-author">Coach</span>
          <Markdown>{wrapUp.text}</Markdown>
        </div>
      )}
    </section>
  )
}

function stateText(moment: MomentInfo): string {
  switch (moment.state) {
    case 'new':
      return 'not started'
    case 'intro':
    case 'attempt':
      return 'in progress'
    case 'solved':
      return 'solved'
    case 'revealed':
      return 'shown'
  }
}
