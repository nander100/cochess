import { createContext, useContext } from 'react'
import Markdown, { type Components, defaultUrlTransform } from 'react-markdown'
import type { Annotation, LineLink, MessageTokens, MoveToken } from '../api/types'
import { useSettings } from '../settings/settingsContext'
import { BoardArrowIcon, PlayIcon } from '../ui'
import './CoachText.css'

const CC_LINK = /^cc:(board|move|line)\/(\d+)$/
const NONE: readonly Annotation[] = []

/** hover: show only this tag while the pointer or focus is on it; click: show it (and go to its
 * position if the board is elsewhere). `null` ends a hover. */
export type ShowTag = (annotation: Annotation | null, how: 'hover' | 'click') => void

/** Play a linked line on the board (SPEC_V3 §9.5). */
export type PlayLine = (link: LineLink) => void

interface CoachTextProps {
  text: string
  /** The message's tokens: move tags, line links and board tags, by placeholder index. */
  tokens?: MessageTokens
  /** Board tags alone (older call sites); `tokens.annotations` wins when both are given. */
  annotations?: readonly Annotation[]
  onShowTag?: ShowTag
  onPlayLine?: PlayLine
}

interface TagContext {
  annotations: readonly Annotation[]
  moves: readonly MoveToken[]
  links: readonly LineLink[]
  onShowTag?: ShowTag
  onPlayLine?: PlayLine
}

const NO_MOVES: readonly MoveToken[] = []
const NO_LINKS: readonly LineLink[] = []
const Tags = createContext<TagContext>({ annotations: [], moves: [], links: [] })

/** A stable link renderer (a new one each render would remount the icons under the pointer and
 * lose hover and focus); it reads the message's tags from context. */
const COMPONENTS: Components = {
  a({ href, children, node: _node, ...rest }) {
    const match = href ? CC_LINK.exec(href) : null
    if (!match) {
      return (
        <a href={href} {...rest}>
          {children}
        </a>
      )
    }
    const index = Number(match[2])
    if (match[1] === 'move') return <MoveTag index={index} />
    if (match[1] === 'line') return <LineTag index={index} />
    return <BoardTag index={index} />
  },
}

/** A coach message as markdown (no raw HTML). Its tags arrive as `cc:` links (PLAN_V3
 * adjustment 1): board tags show as a small board icon, move tags as words or notation by the
 * player's detail level, and line links as buttons that play the line. */
export function CoachText({ text, tokens, annotations = NONE, onShowTag, onPlayLine }: CoachTextProps) {
  const value: TagContext = {
    annotations: tokens?.annotations ?? annotations,
    moves: tokens?.moves ?? NO_MOVES,
    links: tokens?.line_links ?? NO_LINKS,
    onShowTag,
    onPlayLine,
  }
  return (
    <Tags.Provider value={value}>
      <Markdown components={COMPONENTS} urlTransform={keepBoardTags}>
        {text}
      </Markdown>
    </Tags.Provider>
  )
}

function keepBoardTags(url: string): string {
  return CC_LINK.test(url) ? url : defaultUrlTransform(url)
}

/** Notation as a coach would write it: "14...Qxd4", or just "Qxd4" without a number. */
function notation(move: MoveToken): string {
  if (move.move_number === null) return move.san
  return `${move.move_number}${move.white === false ? '...' : '.'}${move.san}`
}

function MoveTag({ index }: { index: number }) {
  const { moves } = useContext(Tags)
  const { settings } = useSettings()
  const move = moves.find((m) => m.index === index)
  if (!move) return null
  const level = settings.effective_detail_level
  if (level === 'technical') {
    return (
      <span className="coach-move coach-move-notation" title={move.words}>
        {notation(move)}
      </span>
    )
  }
  const words = move.sentence_start ? move.words.charAt(0).toUpperCase() + move.words.slice(1) : move.words
  return (
    <span className="coach-move" title={level === 'standard' ? notation(move) : undefined}>
      {words}
    </span>
  )
}

function LineTag({ index }: { index: number }) {
  const { links, onPlayLine } = useContext(Tags)
  const link = links.find((l) => l.index === index)
  if (!link) return null
  if (!onPlayLine) return <span className="coach-line">{link.label}</span>
  return (
    <button type="button" className="coach-line" onClick={() => onPlayLine(link)}>
      <PlayIcon size="small" />
      {link.label}
    </button>
  )
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
