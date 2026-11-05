import { CheckIcon } from './icons'
import './StepChips.css'
import './icons.css'

export interface Step {
  key: string | number
  label: string
  state: 'done' | 'current' | 'upcoming'
}

interface StepChipsProps {
  label: string
  steps: readonly Step[]
  /** Chips become buttons when the steps can be visited. */
  onSelect?: (key: Step['key']) => void
}

/** Moment step chips: done (dark, baby blue check), current (primary), upcoming (outline). */
export function StepChips({ label, steps, onSelect }: StepChipsProps) {
  return (
    <ol className="ui-steps" aria-label={label}>
      {steps.map((step) => {
        const content = (
          <>
            {step.state === 'done' && <CheckIcon size="small" className="ui-step-check" />}
            {step.label}
            {step.state === 'done' && <span className="visually-hidden"> (done)</span>}
          </>
        )
        const className = `ui-step ui-step-${step.state}`
        const current = step.state === 'current' ? 'step' : undefined
        return (
          <li key={step.key}>
            {onSelect ? (
              <button type="button" className={className} aria-current={current} onClick={() => onSelect(step.key)}>
                {content}
              </button>
            ) : (
              <span className={className} aria-current={current}>
                {content}
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
