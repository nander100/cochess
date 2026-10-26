import Markdown from 'react-markdown'

export interface SynopsisState {
  status: 'writing' | 'done' | 'error'
  text: string
  error: string | null
}

interface SynopsisProps {
  state: SynopsisState
  onRetry?: () => void
}

/** The coach's synopsis. Markdown is rendered without raw HTML (react-markdown's default). */
export function Synopsis({ state, onRetry }: SynopsisProps) {
  return (
    <section
      className="synopsis"
      aria-label="Coach's synopsis"
      aria-busy={state.status === 'writing'}
    >
      <h2>Your coach</h2>
      {state.status === 'writing' && state.text === '' && (
        <p className="coach-writing" role="status">
          Coach is writing…
        </p>
      )}
      {state.text && (
        <div className="synopsis-text">
          <Markdown>{state.text}</Markdown>
        </div>
      )}
      {state.status === 'error' && (
        <div className="synopsis-error">
          <p className="run-error" role="alert">
            {state.error}
          </p>
          {onRetry && (
            <button type="button" onClick={onRetry}>
              Try again
            </button>
          )}
        </div>
      )}
    </section>
  )
}
