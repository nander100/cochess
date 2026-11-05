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
import { Button, ChatBubble, CoachAvatar, Eyebrow, FeatureCard, StepChips, TintedPanel, Tooltip, TypingIndicator } from '../ui'
import './MomentStepper.css'
import { isUnsolved, numbered } from './moment'

const MAX_TEXT_CHARS = 2000 // mirrors the backend's limit on reasoning and questions
/** "Get a hint" asks the coach for the next allowed hint (SPEC_V2 §8.2 hint levels). The payload
 * still withholds the answer, so the coach can't name the move. */
export const HINT_REQUEST = "Can I have a hint? Please don't tell me the move."

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
  /** "← Back to game": leave the moments for the coach view. */
  onBack?: () => void
}

/** The critical-moment exercise (SPEC_V2 §8.2): intro → attempts → feedback → reveal → next. */
export function MomentStepper(props: MomentStepperProps) {
  const { gameId, moments, current, onSelect, fen, candidate, onTakeBack, deps, searches, onUpdated, onLoggedOut, onBack } =
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
  const position = moments.indexOf(moment)
  const next = moments[position + 1]
  const open = moment.state === 'intro' || moment.state === 'attempt'
  const failures = moment.attempts.filter((a) => a.grade !== 'best' && a.grade !== 'good').length
  const triesLeft = Math.max(0, moment.max_attempts - failures)
  // The newest coach reply is the feedback card (or the hint panel, after "Get a hint"); what came
  // before stays in the conversation above it.
  const lastCoach = messages.findLastIndex((m) => m.role === 'coach')
  const latest = lastCoach >= 0 ? messages[lastCoach] : null
  const isHint = latest !== null && lastCoach > 0 && messages[lastCoach - 1].text === HINT_REQUEST
  const earlier = messages.filter((_, i) => i !== lastCoach && !(isHint && i === lastCoach - 1))
  // Keep the newest message in view: the log scrolls once the exercise gets long.
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [messages.length, moment.index])

  function hint() {
    if (busy) return
    void step(HINT_REQUEST, () =>
      coachStep((onEvent) => deps.api.momentAsk(gameId, moment.index, HINT_REQUEST, onEvent), setProgress),
    )
  }

  return (
    <section className="moments" aria-label="Critical moments">
      <nav className="moment-steps" aria-label="Critical moment navigation">
        {onBack && (
          <button type="button" className="moment-back" onClick={onBack} disabled={busy}>
            ← Back to game
          </button>
        )}
        <StepChips
          label="Moments in this game"
          steps={moments.map((m, i) => ({
            key: m.index,
            label: `Moment ${i + 1} · ${numbered(m, m.san)}`,
            state: m.index === moment.index ? 'current' : isUnsolved(m) ? 'upcoming' : 'done',
          }))}
          onSelect={(key) => !busy && select(Number(key))}
        />
      </nav>

      <div className="moment-task">
        <Eyebrow>
          Critical moment {position + 1} of {moments.length}
        </Eyebrow>
        <h2 className="moment-title">Find a better move</h2>
        <p className="moment-summary">
          In the game you played <strong>{numbered(moment, moment.san)}</strong> here (
          {moment.label.replace('_', ' ')}: {moment.eval_before} → {moment.eval_after}).
          {open && ' Move a piece on the board to try your answer.'}
        </p>
      </div>

      {(open || moment.state === 'new') && (
        <div className="moment-tries">
          <span className="moment-tries-label">Tries left</span>
          <span className="moment-tries-dots" role="img" aria-label={`${triesLeft} of ${moment.max_attempts} tries left`}>
            {Array.from({ length: moment.max_attempts }, (_, i) => (
              <span key={i} className={i < triesLeft ? 'left' : undefined} />
            ))}
          </span>
        </div>
      )}

      {earlier.length > 0 && (
        <ul ref={log} className="moment-log" aria-live="polite">
          {earlier.map((message, i) => (
            <li key={i}>
              <ChatBubble from={message.role === 'coach' ? 'coach' : 'player'}>
                <Markdown>{message.text}</Markdown>
              </ChatBubble>
            </li>
          ))}
        </ul>
      )}
      {latest && !isHint && (
        <FeatureCard className="moment-feedback" aria-live="polite">
          <CoachAvatar />
          <div className="moment-feedback-text">
            <Markdown>{latest.text}</Markdown>
          </div>
        </FeatureCard>
      )}
      {latest && isHint && (
        <TintedPanel className="moment-hint" aria-live="polite">
          <span className="moment-panel-label">Hint</span>
          <Markdown>{latest.text}</Markdown>
        </TintedPanel>
      )}
      {lastGrade && !busy && <p className={`moment-grade ${lastGrade}`}>{GRADE_LABEL[lastGrade] ?? lastGrade}</p>}
      {progress && <TypingIndicator label={PROGRESS_LABEL[progress]} />}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {!isUnsolved(moment) && moment.best_san && (
        <div className="moment-solution">
          <span className="moment-panel-label">Solution</span>
          <p className="moment-best">
            The engine's move: <strong>{numbered(moment, moment.best_san)}</strong>. Your tries and the engine's move are
            on the board as variations.
          </p>
        </div>
      )}

      {moment.state === 'new' && (
        <Button onClick={start} disabled={busy} className="moment-start">
          Start this moment
        </Button>
      )}

      {open && candidate && (
        <form className="moment-attempt" onSubmit={check}>
          <p>
            Your move: <strong>{numbered(moment, sanOf(fen, candidate))}</strong>
          </p>
          <label className="moment-why-label" htmlFor={`${id}-why`}>
            Why this move? (optional)
          </label>
          <textarea
            id={`${id}-why`}
            className="ui-input ui-textarea"
            value={reasoning}
            maxLength={MAX_TEXT_CHARS}
            rows={2}
            onChange={(event) => setReasoning(event.target.value)}
            disabled={busy}
          />
          <div className="moment-actions">
            <Button type="submit" disabled={busy}>
              Check my move
            </Button>
            <Button variant="outline" onClick={onTakeBack} disabled={busy}>
              Take back
            </Button>
          </div>
        </form>
      )}
      {open && !candidate && (
        <p className="moment-instruction">{busy ? 'Waiting for the coach…' : 'Play your move on the board.'}</p>
      )}

      <div className="moment-actions">
        {open && (
          <>
            <Tooltip text={moment.attempts.length > 0 ? 'The next hint, never the move itself' : 'Try a move first'}>
              <Button variant="outline" onClick={hint} disabled={busy || moment.attempts.length === 0}>
                Get a hint
              </Button>
            </Tooltip>
            <Button variant="secondary" onClick={reveal} disabled={busy}>
              Show the answer
            </Button>
          </>
        )}
        {!isUnsolved(moment) &&
          (next ? (
            <Button className="moment-next" onClick={() => select(next.index)} disabled={busy}>
              Next moment →
            </Button>
          ) : (
            moments.every((m) => !isUnsolved(m)) &&
            !wrapUp && (
              <Button className="moment-next" onClick={finish} disabled={busy}>
                Wrap up
              </Button>
            )
          ))}
      </div>

      {open && (
        <form className="moment-ask" onSubmit={ask}>
          <label className="visually-hidden" htmlFor={`${id}-ask`}>
            Ask the coach about this moment
          </label>
          <input
            id={`${id}-ask`}
            className="ui-input"
            value={question}
            maxLength={MAX_TEXT_CHARS}
            placeholder="Ask the coach about this position…"
            onChange={(event) => setQuestion(event.target.value)}
            disabled={busy}
          />
          <Button type="submit" variant="outline" disabled={busy || !question.trim()}>
            Ask
          </Button>
        </form>
      )}

      {wrapUp && moment.index === last.index && (
        <FeatureCard className="moment-feedback moment-wrap-up">
          <CoachAvatar />
          <div className="moment-feedback-text">
            <Markdown>{wrapUp.text}</Markdown>
          </div>
        </FeatureCard>
      )}
    </section>
  )
}
