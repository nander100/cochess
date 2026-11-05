import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef } from 'react'
import { IconButton } from './Button'
import { CloseIcon } from './icons'
import './Modal.css'

interface ModalProps {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
  /** Buttons at the bottom (e.g. Cancel and the action). */
  actions?: ReactNode
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

/** A modal dialog: focus moves in and stays in, Esc or the close button closes it, and focus
 * returns to where it was. */
export function Modal({ title, open, onClose, children, actions }: ModalProps) {
  const id = useId()
  const dialog = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)

  useEffect(() => {
    close.current = onClose
  })

  useEffect(() => {
    if (!open) return
    const before = document.activeElement as HTMLElement | null
    const first = dialog.current?.querySelector<HTMLElement>(FOCUSABLE)
    first?.focus()
    return () => before?.focus()
  }, [open])

  if (!open) return null

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close.current()
      return
    }
    if (event.key !== 'Tab' || !dialog.current) return
    const items = [...dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.hasAttribute('disabled'))
    if (items.length === 0) return
    const [first, last] = [items[0], items[items.length - 1]]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="ui-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        className="ui-modal"
        onKeyDown={onKeyDown}
      >
        <div className="ui-modal-head">
          <h2 id={`${id}-title`} className="ui-modal-title">
            {title}
          </h2>
          <IconButton label="Close" icon={<CloseIcon />} onClick={onClose} />
        </div>
        <div className="ui-modal-body">{children}</div>
        {actions && <div className="ui-modal-actions">{actions}</div>}
      </div>
    </div>
  )
}
