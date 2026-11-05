import { type KeyboardEvent, useEffect, useRef } from 'react'

interface VariationMenuProps {
  canPromote: boolean
  onPromote: () => void
  onDelete: () => void
  /** Close without acting (Escape, or a click elsewhere). */
  onClose: () => void
}

/** "Promote" and "Delete" for one saved variation (SPEC_V3 §5.1). Opens on its options button
 * or a right-click on the line; arrow keys move between items and Escape closes it. Keys don't
 * reach the board's shortcuts while it's open. */
export function VariationMenu({ canPromote, onPromote, onDelete, onClose }: VariationMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  })

  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest' })
    ref.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({ preventScroll: true })
    const outside = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) close.current()
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [])

  function keys(event: KeyboardEvent) {
    event.stopPropagation()
    if (event.key === 'Escape') close.current()
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    const items = [...(ref.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])]
    const at = items.indexOf(document.activeElement as HTMLButtonElement)
    const step = event.key === 'ArrowDown' ? 1 : -1
    items[(at + step + items.length) % items.length]?.focus()
  }

  return (
    <div ref={ref} role="menu" aria-label="Variation" className="variation-menu" onKeyDown={keys}>
      <button type="button" role="menuitem" disabled={!canPromote} onClick={onPromote}>
        Promote to main line of my notes
      </button>
      <button type="button" role="menuitem" onClick={onDelete}>
        Delete variation
      </button>
    </div>
  )
}
