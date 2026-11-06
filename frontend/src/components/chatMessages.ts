import type { Annotation, ChatEntry } from '../api/types'

/** A message as the chat panel shows it. */
export interface ChatMessage {
  role: 'player' | 'coach'
  text: string
  /** Where on the board a player's message was sent from ("after 14. Nf3"). */
  where?: string | null
  /** The board position (node id: UCI moves joined by spaces) the message is about. */
  path?: string | null
  /** A coach answer's board tags (SPEC_V3 §6). */
  annotations?: Annotation[]
}

/** The stored conversation as the panel shows it. */
export function chatMessages(entries: readonly ChatEntry[]): ChatMessage[] {
  return entries.map(({ role, text, where, path_uci, annotations }) => ({
    role,
    text,
    where,
    path: path_uci ? path_uci.join(' ') : null,
    annotations: annotations ?? [],
  }))
}
