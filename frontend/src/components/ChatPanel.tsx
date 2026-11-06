import { type FormEvent, useEffect, useId, useState } from 'react'
import type { ChatProgress } from '../analysis/chat'
import type { Annotation, CoachReply } from '../api/types'
import { Button, ChatBubble, TintedPanel, TypingIndicator } from '../ui'
import './ChatPanel.css'
import type { ChatMessage } from './chatMessages'
import { CoachText, type PlayLine } from './CoachText'

const MAX_MESSAGE_CHARS = 2000 // mirrors backend CoachSettings.chat_max_message_chars
const EXPLAIN_TEXT = 'Explain this position'

/** A board tag was hovered (annotation, or null when the hover ends) or clicked, in a message
 * about the position `path`. */
export type ShowChatTag = (path: string, annotation: Annotation | null, how: 'hover' | 'click') => void

interface ChatPanelProps {
  ask: (message: string, onProgress: (progress: ChatProgress) => void) => Promise<CoachReply>
  /** Explain the position on the board (SPEC_V2 §6.3); the answer appears in the chat. */
  explain?: (onProgress: (progress: ChatProgress) => void) => Promise<CoachReply>
  /** The position on the board, as messages sent now are labelled ("after 14. Nf3"). */
  where?: string
  /** The position on the board, as a node id: what messages sent now are about. */
  path?: string
  /** A coach answer arrived for the position `path`. */
  onReply?: (path: string, reply: CoachReply) => void
  onShowTag?: ShowChatTag
  /** Play a linked line on the board (SPEC_V3 §9.5). */
  onPlayLine?: PlayLine
  /** The conversation so far, when reopening a game. */
  initial?: readonly ChatMessage[]
  /** Told the current Explain action (null when it can't run now), for the X shortcut. */
  onExplainReady?: (explain: (() => void) | null) => void
}

const PROGRESS_LABEL: Record<ChatProgress, string> = {
  looking: 'Coach is looking at the position…',
  writing: 'Coach is writing…',
  thinking: 'Coach is thinking deeply…',
}

/** Questions about the position on the board, and the Explain button (SPEC_V2 §6). */
export function ChatPanel({
  ask, explain, where, path, initial = [], onExplainReady, onReply, onShowTag, onPlayLine,
}: ChatPanelProps) {
  const id = useId()
  const [messages, setMessages] = useState<ChatMessage[]>(() => [...initial])
  const [draft, setDraft] = useState('')
  const [progress, setProgress] = useState<ChatProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const busy = progress !== null

  async function send(text: string, run: (onProgress: (p: ChatProgress) => void) => Promise<CoachReply>) {
    setError(null)
    const sentFrom = path ?? null
    setMessages((previous) => [...previous, { role: 'player', text, where, path: sentFrom }])
    try {
      const reply = await run(setProgress)
      setMessages((previous) => [
        ...previous,
        {
          role: 'coach', text: reply.text, path: sentFrom, annotations: reply.annotations,
          moves: reply.moves ?? [], line_links: reply.line_links ?? [],
        }, // prettier-ignore
      ])
      if (sentFrom !== null) onReply?.(sentFrom, reply)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Something went wrong.')
    } finally {
      setProgress(null)
    }
  }

  // X: Explain the position, when the button would work.
  useEffect(() => {
    if (!onExplainReady) return undefined
    onExplainReady(explain && !busy ? () => void send(EXPLAIN_TEXT, explain) : null)
    return () => onExplainReady(null)
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = draft.trim()
    if (!message || busy) return
    setDraft('')
    void send(message, (onProgress) => ask(message, onProgress))
  }

  return (
    <TintedPanel as="section" className="chat" aria-label="Chat with your coach">
      <div className="chat-header">
        <h2 className="chat-title">Ask your coach about this position</h2>
        {explain && (
          <Button variant="outline" disabled={busy} onClick={() => void send(EXPLAIN_TEXT, explain)}>
            {EXPLAIN_TEXT}
          </Button>
        )}
      </div>
      {where && <p className="chat-where-now">Your questions are about the board: {where}.</p>}
      <ol className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <li className="chat-hint">
            Move to any position and ask about it, or try an idea on the board: “What if I take on e5?”
          </li>
        )}
        {messages.map((message, index) => {
          const about = message.path
          const showTag =
            onShowTag && about != null
              ? (annotation: Annotation | null, how: 'hover' | 'click') => onShowTag(about, annotation, how)
              : undefined
          return (
          <li key={index}>
            <ChatBubble from={message.role}>
              {message.where && <span className="chat-where">{message.where}</span>}
              {message.role === 'coach' ? (
                <CoachText text={message.text} tokens={message} onShowTag={showTag} onPlayLine={onPlayLine} />
              ) : (
                <p>{message.text}</p>
              )}
            </ChatBubble>
          </li>
          )
        })}
      </ol>
      {progress && <TypingIndicator label={PROGRESS_LABEL[progress]} />}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form className="chat-form" onSubmit={handleSubmit}>
        <label htmlFor={`${id}-message`} className="visually-hidden">
          Your question
        </label>
        <textarea
          id={`${id}-message`}
          className="ui-input ui-textarea chat-input"
          data-shortcut="chat"
          rows={1}
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
        <Button type="submit" variant="secondary" disabled={busy || draft.trim() === ''}>
          Send
        </Button>
      </form>
    </TintedPanel>
  )
}
