import { type FormEvent, useId, useState } from 'react'
import Markdown from 'react-markdown'
import type { ChatProgress } from '../analysis/chat'

const MAX_MESSAGE_CHARS = 2000 // mirrors backend CoachSettings.chat_max_message_chars
const EXPLAIN_TEXT = 'Explain this position'

export interface ChatMessage {
  role: 'player' | 'coach'
  text: string
  /** Where on the board a player's message was sent from ("after 14. Nf3"). */
  where?: string | null
}

interface ChatPanelProps {
  ask: (message: string, onProgress: (progress: ChatProgress) => void) => Promise<string>
  /** Explain the position on the board (SPEC_V2 §6.3); the answer appears in the chat. */
  explain?: (onProgress: (progress: ChatProgress) => void) => Promise<string>
  /** The position on the board, as messages sent now are labelled ("after 14. Nf3"). */
  where?: string
  /** The conversation so far, when reopening a game. */
  initial?: readonly ChatMessage[]
}

const PROGRESS_LABEL: Record<ChatProgress, string> = {
  looking: 'Coach is looking at the position…',
  writing: 'Coach is writing…',
  thinking: 'Coach is thinking deeply…',
}

/** Questions about the position on the board, and the Explain button (SPEC_V2 §6). */
export function ChatPanel({ ask, explain, where, initial = [] }: ChatPanelProps) {
  const id = useId()
  const [messages, setMessages] = useState<ChatMessage[]>(() => [...initial])
  const [draft, setDraft] = useState('')
  const [progress, setProgress] = useState<ChatProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const busy = progress !== null

  async function send(text: string, run: (onProgress: (p: ChatProgress) => void) => Promise<string>) {
    setError(null)
    setMessages((previous) => [...previous, { role: 'player', text, where }])
    try {
      const reply = await run(setProgress)
      setMessages((previous) => [...previous, { role: 'coach', text: reply }])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
    } finally {
      setProgress(null)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || busy) return
    setDraft('')
    void send(message, (onProgress) => ask(message, onProgress))
  }

  return (
    <section className="chat" aria-label="Chat with your coach">
      <div className="chat-header">
        <h2>Ask your coach</h2>
        {explain && (
          <button type="button" className="explain" disabled={busy} onClick={() => void send(EXPLAIN_TEXT, explain)}>
            {EXPLAIN_TEXT}
          </button>
        )}
      </div>
      {where && <p className="chat-where-now">Your questions are about the board: {where}.</p>}
      <ol className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <li className="chat-hint">
            Move to any position and ask about it, or try an idea on the board: “What if I take on e5?”
          </li>
        )}
        {messages.map((message, index) => (
          <li key={index} className={`chat-message ${message.role}`}>
            <span className="chat-author">
              {message.role === 'player' ? 'You' : 'Coach'}
              {message.where && <span className="chat-where"> · {message.where}</span>}
            </span>
            {message.role === 'coach' ? <Markdown>{message.text}</Markdown> : <p>{message.text}</p>}
          </li>
        ))}
      </ol>
      {progress && (
        <p className="coach-writing" role="status">
          {PROGRESS_LABEL[progress]}
        </p>
      )}
      {error && (
        <p className="run-error" role="alert">
          {error}
        </p>
      )}
      <form className="chat-form" onSubmit={handleSubmit}>
        <label htmlFor={`${id}-message`} className="visually-hidden">
          Your question
        </label>
        <textarea
          id={`${id}-message`}
          rows={2}
          maxLength={MAX_MESSAGE_CHARS}
          placeholder="Ask about this position…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              e.currentTarget.form?.requestSubmit()
            }
          }}
          disabled={busy}
        />
        <button type="submit" disabled={busy || draft.trim() === ''}>
          Send
        </button>
      </form>
    </section>
  )
}
