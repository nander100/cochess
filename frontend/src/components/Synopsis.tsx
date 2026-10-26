import Markdown from 'react-markdown'

export interface SynopsisState {
  status: 'writing' | 'done' | 'error'
  text: string
  error: string | null
}

interface SynopsisProps {
  state: SynopsisState
}

/** The coach's synopsis. Markdown is rendered without raw HTML (react-markdown's default). */
export function Synopsis({ state }: SynopsisProps) {
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
        <p className="run-error" role="alert">
          {state.error}
        </p>
      )}
    </section>
  )
}
