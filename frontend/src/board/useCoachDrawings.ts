import { useCallback, useState } from 'react'
import type { Annotation, ChatEntry } from '../api/types'
import { chatMessages } from '../components/chatMessages'
import { latestByPath } from './coachShapes'

const NONE: readonly Annotation[] = []

interface Focus {
  path: string
  annotations: readonly Annotation[] // one tag: the one hovered or clicked
}

export interface CoachDrawings {
  /** A coach answer about `path` arrived; its tags replace what was drawn there. */
  record: (path: string, annotations: readonly Annotation[]) => void
  /** Show only this tag (hover or click), or go back to the whole message (null). */
  focus: (path: string, annotation: Annotation | null) => void
  /** What to draw at `boardPath` (null: nothing), from the chat's drawings or `drawings`. */
  shown: (boardPath: string | null, drawings?: ReadonlyMap<string, readonly Annotation[]>) => readonly Annotation[]
}

/** The coach's shapes on the board (SPEC_V3 §6.3): a new message's tags are drawn; hovering a
 * tag shows only that tag; shapes belong to the position they were drawn for, so they clear when
 * the board moves away and come back when it returns. */
export function useCoachDrawings(initialChat: readonly ChatEntry[]): CoachDrawings {
  const [chat, setChat] = useState<ReadonlyMap<string, readonly Annotation[]>>(() =>
    latestByPath(chatMessages(initialChat)),
  )
  const [focused, setFocused] = useState<Focus | null>(null)

  const record = useCallback((path: string, annotations: readonly Annotation[]) => {
    setChat((previous) => new Map(previous).set(path, [...annotations]))
    setFocused(null)
  }, [])
  const focus = useCallback((path: string, annotation: Annotation | null) => {
    setFocused(annotation ? { path, annotations: [annotation] } : null)
  }, [])

  function shown(boardPath: string | null, drawings: ReadonlyMap<string, readonly Annotation[]> = chat) {
    if (boardPath === null) return NONE
    if (focused?.path === boardPath) return focused.annotations
    return drawings.get(boardPath) ?? NONE
  }

  return { record, focus, shown }
}
