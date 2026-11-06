import { type ReactNode, useEffect, useRef, useState } from 'react'
import type { Color, MoveLabel } from '../api/types'
import { MoreIcon } from '../ui'
import './MoveList.css'
import { type GameTree, ROOT, type TreeNode, lineFrom } from './tree'
import { canPromote, startsVariation } from './variations'
import { VariationMenu } from './VariationMenu'

const GLYPH: Record<MoveLabel, string> = {
  inaccuracy: '?!',
  mistake: '?',
  blunder: '??',
  missed_mate: '#?',
}

const LABEL_TEXT: Record<MoveLabel, string> = {
  inaccuracy: 'inaccuracy',
  mistake: 'mistake',
  blunder: 'blunder',
  missed_mate: 'missed a forced mate',
}

interface MoveListProps {
  tree: GameTree
  current: string
  userColor: Color
  onSelect: (nodeId: string) => void
  /** Saved-variation actions (SPEC_V3 §5.1), by the variation's first node. */
  onDelete?: (startId: string) => void
  onPromote?: (startId: string) => void
  /** Walk through the variation starting at this node (SPEC_V3 §7.1). */
  onWalk?: (startId: string) => void
}

/** The game's moves with the player's mistakes marked, and explored variations inline (SPEC_V2 §5.3). */
export function MoveList({ tree, current, userColor, onSelect, onDelete, onPromote, onWalk }: MoveListProps) {
  const [menu, setMenu] = useState<string | null>(null)
  const root = tree.nodes[ROOT]
  if (root.children.length === 0) return <p className="move-list">No moves.</p>
  const act = (action: ((startId: string) => void) | undefined, startId: string) => {
    setMenu(null)
    action?.(startId)
  }
  const shared: Shared = {
    tree, current, userColor, onSelect, menu,
    onMenu: onDelete && onPromote ? setMenu : null,
    onDelete: (id) => act(onDelete, id),
    onPromote: (id) => act(onPromote, id),
    onWalk: onWalk ? (id) => act(onWalk, id) : null,
  } // prettier-ignore
  return (
    <div className="move-list" aria-label="Moves">
      <Line {...shared} startId={root.children[0]} />
      {root.children.slice(1).map((id) => (
        <Variation key={id} {...shared} startId={id} />
      ))}
    </div>
  )
}

interface Shared {
  tree: GameTree
  current: string
  userColor: Color
  onSelect: (nodeId: string) => void
  /** The variation whose menu is open. */
  menu: string | null
  /** Open (or, with null, close) a variation's menu; null when there are no actions. */
  onMenu: ((startId: string | null) => void) | null
  onDelete: (startId: string) => void
  onPromote: (startId: string) => void
  onWalk: ((startId: string) => void) | null
}

interface LineProps extends Shared {
  startId: string
}

/** A line of moves; after each move, the variations that replace it, indented. */
function Line(props: LineProps) {
  const { tree, startId, current, userColor, onSelect } = props
  const items: ReactNode[] = []
  let numberNext = true // the first move of a line, and the move after a variation, show a number
  for (const node of lineFrom(tree, startId)) {
    const parent = node.parent === null ? undefined : tree.nodes[node.parent]
    if (parent && node.id !== startId && parent.mainline && startsVariation(tree, node)) {
      // The game ended here and the player played on: those lines are variations like the rest.
      for (const id of parent.children) items.push(<Variation key={`v-${id}`} {...props} startId={id} />)
      break
    }
    items.push(
      <Move
        key={node.id}
        node={node}
        withNumber={numberNext || node.ply % 2 === 1}
        current={node.id === current}
        userColor={userColor}
        onSelect={onSelect}
      />,
    )
    numberNext = false
    if (parent && parent.children[0] === node.id && parent.children.length > 1) {
      for (const alternative of parent.children.slice(1)) {
        items.push(<Variation key={`v-${alternative}`} {...props} startId={alternative} />)
      }
      numberNext = true
    }
  }
  return <>{items}</>
}

/** A saved variation, indented, with its options button; right-click opens the same menu. */
function Variation(props: LineProps) {
  const { tree, startId, menu, onMenu, onDelete, onPromote, onWalk } = props
  const trigger = useRef<HTMLButtonElement>(null)
  const open = menu === startId
  const closeMenu = () => {
    onMenu?.(null)
    trigger.current?.focus()
  }
  return (
    <div
      className="variation"
      role="group"
      aria-label="Variation"
      onContextMenu={(event) => {
        if (!onMenu) return
        event.preventDefault()
        event.stopPropagation() // the innermost variation under the pointer
        onMenu(startId)
      }}
    >
      {onMenu && (
        <button
          ref={trigger}
          type="button"
          className="variation-options"
          aria-label="Variation options"
          title="Variation options"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => onMenu(open ? null : startId)}
        >
          <MoreIcon size="small" />
        </button>
      )}
      <Line {...props} />
      {/* In the flow, under its line: the move list scrolls, so a popover would be clipped. */}
      {open && (
        <VariationMenu
          canPromote={canPromote(tree, startId)}
          onPromote={() => onPromote(startId)}
          onDelete={() => onDelete(startId)}
          onWalk={onWalk ? () => onWalk(startId) : undefined}
          onClose={closeMenu}
        />
      )}
    </div>
  )
}

interface MoveProps {
  node: TreeNode
  withNumber: boolean
  current: boolean
  userColor: Color
  onSelect: (nodeId: string) => void
}

function Move({ node, withNumber, current, userColor, onSelect }: MoveProps) {
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (current) ref.current?.scrollIntoView?.({ block: 'nearest' })
  }, [current])

  const side: Color = node.ply % 2 === 1 ? 'white' : 'black'
  const moveNumber = Math.floor((node.ply + 1) / 2)
  // Glyphs mark the player's own mistakes in the game (SPEC_V2 §5.3).
  const label = node.mainline && side === userColor ? node.label : null
  const number = withNumber ? `${moveNumber}${side === 'white' ? '.' : '...'}` : null
  const description = `${moveNumber}${side === 'white' ? '.' : '...'} ${node.san}${label ? `, ${LABEL_TEXT[label]}` : ''}`
  return (
    <>
      {number && <span className="move-number">{number}</span>}
      <button
        ref={ref}
        type="button"
        className={`move${label ? ` ${label}` : ''}${node.mainline ? '' : ' explored'}`}
        aria-current={current ? 'step' : undefined}
        aria-label={description}
        onClick={() => onSelect(node.id)}
      >
        {node.san}
        {label && <span className="glyph">{GLYPH[label]}</span>}
      </button>
    </>
  )
}
