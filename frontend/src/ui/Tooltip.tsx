import { type ReactElement, cloneElement, useId, useState } from 'react'
import './Tooltip.css'

interface TooltipProps {
  text: string
  /** One focusable element; the tooltip describes it. */
  children: ReactElement<{ 'aria-describedby'?: string }>
}

/** A short description shown on hover and on keyboard focus; Esc hides it. */
export function Tooltip({ text, children }: TooltipProps) {
  const id = useId()
  const [open, setOpen] = useState(false)
  return (
    <span
      className="ui-tooltip-anchor"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false)
      }}
    >
      {cloneElement(children, { 'aria-describedby': id })}
      <span role="tooltip" id={id} className="ui-tooltip" hidden={!open}>
        {text}
      </span>
    </span>
  )
}
