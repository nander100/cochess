import { useId } from 'react'
import './Switch.css'

interface SwitchProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  /** A line under the label. */
  help?: string
}

/** An on/off switch built on a native checkbox, so it reads as one for keyboards and screen
 * readers. */
export function Switch({ label, checked, onChange, disabled = false, help }: SwitchProps) {
  const id = useId()
  return (
    <label htmlFor={id} className="ui-switch">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-describedby={help ? `${id}-help` : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="ui-switch-track" aria-hidden="true" />
      <span className="ui-switch-text">
        {label}
        {help && (
          <span id={`${id}-help`} className="ui-switch-help">
            {help}
          </span>
        )}
      </span>
    </label>
  )
}
