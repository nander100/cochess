import type { Walkthrough } from '../api/types'
import { CoachText } from '../components/CoachText'
import { numberedSan } from '../engine/live'
import { Button, ErrorState, Eyebrow, FeatureCard, ProgressBar, StepChips, TypingIndicator } from '../ui'
import type { WalkState } from './useWalkthrough'
import './WalkthroughPanel.css'

interface WalkthroughPanelProps {
  walk: WalkState
  onStep: (step: number) => void
  onClose: () => void
  onSave: () => void
  onRetry: () => void
}

/** The walkthrough stepper (SPEC_V3 §7.3): the intro, then one step per move with the board on
 * that step's position. It takes the place of the coach and moments tabs while it's open. */
export function WalkthroughPanel({ walk, onStep, onClose, onSave, onRetry }: WalkthroughPanelProps) {
  return (
    <section className="walkthrough" aria-label="Walkthrough">
      <div className="walkthrough-header">
        <Eyebrow>Walkthrough</Eyebrow>
        <Button variant="outline" onClick={onClose}>
          Back to game
        </Button>
      </div>
      {walk.result ? (
        <Ready result={walk.result} walk={walk} onStep={onStep} onSave={onSave} />
      ) : (
        <Loading walk={walk} onRetry={onRetry} />
      )}
      <p className="walkthrough-keys">← → to step through, Esc to go back to the game.</p>
    </section>
  )
}

function Loading({ walk, onRetry }: { walk: WalkState; onRetry: () => void }) {
  if (walk.error) return <ErrorState message={walk.error} onRetry={onRetry} />
  const progress = walk.progress
  if (progress?.kind === 'scanning') {
    return (
      <ProgressBar
        label={`The engine is checking each position (${progress.done + 1} of ${progress.total})…`}
        done={progress.done}
        total={progress.total}
      />
    )
  }
  return <TypingIndicator label="Coach is writing the walkthrough…" />
}

interface ReadyProps {
  result: Walkthrough
  walk: WalkState
  onStep: (step: number) => void
  onSave: () => void
}

function Ready({ result, walk, onStep, onSave }: ReadyProps) {
  const total = result.steps.length
  const current = walk.step === 0 ? null : result.steps[walk.step - 1]
  const before = walk.step <= 1 ? result.start_fen : result.steps[walk.step - 2].fen_after
  const chips = [{ key: 0, label: 'Intro' }, ...result.steps.map((s) => ({ key: s.index, label: s.san }))].map(
    (chip) => ({
      ...chip,
      state: chip.key < walk.step ? ('done' as const) : chip.key === walk.step ? ('current' as const) : ('upcoming' as const),
    }),
  )
  return (
    <>
      <h2 className="walkthrough-line">{numberedSan(result.start_fen, result.line_uci)}</h2>
      <StepChips label="Steps" steps={chips} onSelect={(key) => onStep(Number(key))} />
      <FeatureCard className="walkthrough-text" aria-live="polite">
        {current ? (
          <>
            <p className="walkthrough-step-label">
              Step {current.index} of {total}: {numberedSan(before, [current.uci])}
              {current.eval_after && <span className="walkthrough-eval"> · {current.eval_after}</span>}
            </p>
            <CoachText text={current.text} />
            {walk.step === total && (
              <div className="walkthrough-summary">
                <strong>The takeaway</strong>
                <CoachText text={result.summary} />
              </div>
            )}
          </>
        ) : (
          <CoachText text={result.intro} />
        )}
      </FeatureCard>
      <div className="walkthrough-nav">
        <Button variant="outline" disabled={walk.step === 0} onClick={() => onStep(walk.step - 1)}>
          ◀ Previous
        </Button>
        <Button disabled={walk.step === total} onClick={() => onStep(walk.step + 1)}>
          {walk.step === 0 ? 'Start ▶' : 'Next ▶'}
        </Button>
        <Button variant="secondary" disabled={walk.saved} onClick={onSave}>
          {walk.saved ? 'Saved as a variation' : 'Save as variation'}
        </Button>
      </div>
    </>
  )
}
