import type { ReactNode } from 'react'
import type { MessageTokens } from '../api/types'
import { Button, CoachAvatar, FeatureCard, TypingIndicator } from '../ui'
import { CoachText, type PlayLine } from './CoachText'
import './Synopsis.css'

export interface SynopsisState {
  status: 'writing' | 'done' | 'error'
  text: string
  error: string | null
  /** Its move tags and line links (SPEC_V3 §9.4), once the text is checked. */
  tokens?: MessageTokens
}

interface SynopsisProps {
  state: SynopsisState
  onRetry?: () => void
  /** Shown under the text, e.g. "Practice 3 critical moments". */
  action?: ReactNode
  onPlayLine?: PlayLine
}

/** The coach's synopsis as the design's "Coach's summary" feature card. Markdown is rendered
 * without raw HTML (react-markdown's default). */
export function Synopsis({ state, onRetry, action, onPlayLine }: SynopsisProps) {
  return (
    <FeatureCard as="section" className="synopsis" aria-label="Coach's synopsis" aria-busy={state.status === 'writing'}>
      <CoachSummaryHeading />
      {state.status === 'writing' && state.text === '' && <TypingIndicator label="Coach is writing…" />}
      {state.text && (
        <div className="synopsis-text">
          <CoachText text={state.text} tokens={state.tokens} onPlayLine={onPlayLine} />
        </div>
      )}
      {state.status === 'error' && (
        <div className="synopsis-error">
          <p role="alert">{state.error}</p>
          {onRetry && (
            <Button className="synopsis-action" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      )}
      {state.status === 'done' && action}
    </FeatureCard>
  )
}

export function CoachSummaryHeading() {
  return (
    <div className="synopsis-heading">
      <CoachAvatar />
      <h2>Coach's summary</h2>
    </div>
  )
}
