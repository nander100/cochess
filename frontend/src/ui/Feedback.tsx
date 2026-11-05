import type { ReactNode } from 'react'
import { Button } from './Button'
import { AlertIcon } from './icons'
import './Feedback.css'

/** Progress with a filled bar on the track color. `label` is shown and read out. */
export function ProgressBar({ label, done, total }: { label: string; done: number; total: number }) {
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  return (
    <div className="ui-progress">
      <p className="ui-progress-label" role="status">
        {label}
      </p>
      <div
        className="ui-progress-track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={Math.min(done, total)}
      >
        <div className="ui-progress-fill" style={{ inlineSize: `${percent}%` }} />
      </div>
    </div>
  )
}

/** Placeholder blocks while data loads; hidden from screen readers (the page announces loading). */
export function Skeleton({ lines = 3, label = 'Loading…' }: { lines?: number; label?: string }) {
  return (
    <div className="ui-skeleton" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="ui-skeleton-line" aria-hidden="true" />
      ))}
    </div>
  )
}

/** Nothing here yet: says what to do next. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="ui-empty">
      <h2 className="ui-empty-title">{title}</h2>
      {children && <div className="ui-empty-body">{children}</div>}
      {action && <div className="ui-empty-action">{action}</div>}
    </div>
  )
}

/** Something failed: a plain message and, when it can help, a retry. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="ui-error" role="alert">
      <AlertIcon />
      <p>{message}</p>
      {onRetry && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

/** Three pulsing dots while the coach writes (its reply is checked before it's shown). */
export function TypingIndicator({ label = 'Coach is writing…' }: { label?: string }) {
  return (
    <div className="ui-typing" role="status">
      <span className="ui-typing-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="ui-typing-label">{label}</span>
    </div>
  )
}
