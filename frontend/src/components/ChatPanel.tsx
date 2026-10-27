import { type FormEvent, useId, useState } from 'react'
import Markdown from 'react-markdown'
import type { ChatProgress } from '../analysis/chat'

const MAX_MESSAGE_CHARS = 2000 // mirrors backend CoachSettings.chat_max_message_chars

export interface ChatMessage {
  role: 'player' | 'coach'
  text: string
}

interface ChatPanelProps {
  ask: (message: string, onProgress: (progress: ChatProgress) => void) => Promise<string>
  /** The conversation so far, when reopening a game. */
  initial?: readonly ChatMessage[]
}

const PROGRESS_LABEL: Record<ChatProgress, string> = {
  writing: 'Coach is writing…',
  thinking: 'Coach is thinking deeply…',
}

/** Follow-up questions about the game, beside the synopsis (SPEC §2, §8). */
export function ChatPanel({ ask, initial = [] }: ChatPanelProps) {
  const id = useId()
  const [messages, setMessages] = useState<ChatMessage[]>(() => [...initial])
  const [draft, setDraft] = useState('')
  const [progress, setProgress] = useState<ChatProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const busy = progress !== null

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || busy) return
    setDraft('')
    setError(null)
    setMessages((previous) => [...previous, { role: 'player', text: message }])
    try {
      const reply = await ask(message, setProgress)
      setMessages((previous) => [...previous, { role: 'coach', text: reply }])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
    } finally {
      setProgress(null)
    }
  }

  return (
    <section className="chat" aria-label="Chat with your coach">
      <h2>Ask your coach</h2>
      <ol className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <li className="chat-hint">
            Ask about any move, or try an idea: “What if I had played Nxe5 on move 14?”
          </li>
        )}
        {messages.map((message, index) => (
          <li key={index} className={`chat-message ${message.role}`}>
            <span className="chat-author">{message.role === 'player' ? 'You' : 'Coach'}</span>
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
          placeholder="Ask about your game…"
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
