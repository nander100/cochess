import { type ReactNode, useEffect, useRef } from 'react'
import type { Color, MoveLabel } from '../api/types'
import { type GameTree, ROOT, type TreeNode, lineFrom } from './tree'

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
}

/** The game's moves with the player's mistakes marked, and explored variations inline (SPEC_V2 §5.3). */
export function MoveList({ tree, current, userColor, onSelect }: MoveListProps) {
  const root = tree.nodes[ROOT]
  if (root.children.length === 0) return <p className="move-list">No moves.</p>
  return (
    <div className="move-list" aria-label="Moves">
      <Line tree={tree} startId={root.children[0]} {...{ current, userColor, onSelect }} />
      {root.children.slice(1).map((id) => (
        <Variation key={id} tree={tree} startId={id} {...{ current, userColor, onSelect }} />
      ))}
    </div>
  )
}

interface LineProps extends Omit<MoveListProps, 'tree'> {
  tree: GameTree
  startId: string
}

/** A line of moves; after each move, the variations that replace it, indented. */
function Line({ tree, startId, current, userColor, onSelect }: LineProps) {
  const items: ReactNode[] = []
  let numberNext = true // the first move of a line, and the move after a variation, show a number
  for (const node of lineFrom(tree, startId)) {
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
    const parent = node.parent === null ? undefined : tree.nodes[node.parent]
    if (parent && parent.children[0] === node.id && parent.children.length > 1) {
      for (const alternative of parent.children.slice(1)) {
        items.push(
          <Variation
            key={`v-${alternative}`}
            tree={tree}
            startId={alternative}
            current={current}
            userColor={userColor}
            onSelect={onSelect}
          />,
        )
      }
      numberNext = true
    }
  }
  return <>{items}</>
}

function Variation(props: LineProps) {
  return (
    <div className="variation" role="group" aria-label="Variation">
      <Line {...props} />
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
