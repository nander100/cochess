import { useId } from 'react'
import './SegmentedToggle.css'

export interface ToggleOption<T extends string> {
  value: T
  label: string
}

interface SegmentedToggleProps<T extends string> {
  legend: string
  options: readonly ToggleOption<T>[]
  /** null: nothing selected (the color choice never has a default, SPEC_V3 §4.6). */
  value: T | null
  onChange: (value: T) => void
  disabled?: boolean
  /** Visually hide the legend when the surrounding text already names the choice. */
  hideLegend?: boolean
  describedBy?: string
}

/** A row of toggle buttons from the design (Profile's time control and Appearance), built on
 * native radio inputs so it reads and behaves as one choice for keyboards and screen readers. */
export function SegmentedToggle<T extends string>({
  legend,
  options,
  value,
  onChange,
  disabled = false,
  hideLegend = false,
  describedBy,
}: SegmentedToggleProps<T>) {
  const name = useId()
  return (
    <fieldset className="ui-toggle" disabled={disabled} aria-describedby={describedBy}>
      <legend className={hideLegend ? 'visually-hidden' : 'ui-toggle-legend'}>{legend}</legend>
      <div className="ui-toggle-options">
        {options.map((option) => (
          <label key={option.value} className="ui-toggle-option">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
