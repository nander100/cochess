import { createContext, useContext } from 'react'
import Markdown, { type Components, defaultUrlTransform } from 'react-markdown'
import type { Annotation } from '../api/types'
import { BoardArrowIcon } from '../ui'
import './CoachText.css'

const BOARD_TAG = /^cc:board\/(\d+)$/
const NONE: readonly Annotation[] = []

/** hover: show only this tag while the pointer or focus is on it; click: show it (and go to its
 * position if the board is elsewhere). `null` ends a hover. */
export type ShowTag = (annotation: Annotation | null, how: 'hover' | 'click') => void

interface CoachTextProps {
  text: string
  annotations?: readonly Annotation[]
  onShowTag?: ShowTag
}

interface TagContext {
  annotations: readonly Annotation[]
  onShowTag?: ShowTag
}

const Tags = createContext<TagContext>({ annotations: [] })

/** A stable link renderer (a new one each render would remount the icons under the pointer and
 * lose hover and focus); it reads the message's tags from context. */
const COMPONENTS: Components = {
  a({ href, children, node: _node, ...rest }) {
    const match = href ? BOARD_TAG.exec(href) : null
    if (!match) {
      return (
        <a href={href} {...rest}>
          {children}
        </a>
      )
    }
    return <BoardTag index={Number(match[1])} />
  },
}

/** A coach message as markdown (no raw HTML). Each board tag arrives as a `cc:board/N` link
 * (PLAN_V3 adjustment 1) and is shown as a small board icon at its place in the text. */
export function CoachText({ text, annotations = NONE, onShowTag }: CoachTextProps) {
  return (
    <Tags.Provider value={{ annotations, onShowTag }}>
      <Markdown components={COMPONENTS} urlTransform={keepBoardTags}>
        {text}
      </Markdown>
    </Tags.Provider>
  )
}

function keepBoardTags(url: string): string {
  return BOARD_TAG.test(url) ? url : defaultUrlTransform(url)
}

function BoardTag({ index }: { index: number }) {
  const { annotations, onShowTag } = useContext(Tags)
  const annotation = annotations.find((a) => a.tag_index === index)
  if (!annotation) return null
  if (!onShowTag) {
    return (
      <span className="coach-board-tag">
        <BoardArrowIcon size="small" />
      </span>
    )
  }
  return (
    <button
      type="button"
      className="coach-board-tag"
      aria-label="Show this on the board"
      title="Show this on the board"
      onMouseEnter={() => onShowTag(annotation, 'hover')}
      onMouseLeave={() => onShowTag(null, 'hover')}
      onFocus={() => onShowTag(annotation, 'hover')}
      onBlur={() => onShowTag(null, 'hover')}
      onClick={() => onShowTag(annotation, 'click')}
    >
      <BoardArrowIcon size="small" />
    </button>
  )
}
