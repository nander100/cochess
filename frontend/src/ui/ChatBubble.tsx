import type { ReactNode } from 'react'
import './ChatBubble.css'

/** The coach's avatar: a baby blue circle with a bold "C". */
export function CoachAvatar() {
  return (
    <span className="ui-coach-avatar" aria-hidden="true">
      C
    </span>
  )
}

/** A chat message: the player's on the right in primary, the coach's on the left in the field
 * color with a tinted outline. */
export function ChatBubble({ from, children }: { from: 'player' | 'coach'; children: ReactNode }) {
  return (
    <div className={`ui-bubble-row ui-bubble-row-${from}`}>
      {from === 'coach' && <CoachAvatar />}
      <div className={`ui-bubble ui-bubble-${from}`}>
        <span className="visually-hidden">{from === 'coach' ? 'Coach: ' : 'You: '}</span>
        {children}
      </div>
    </div>
  )
}
