import { type KeyboardEvent, type ReactNode, useId, useRef } from 'react'
import './Tabs.css'

export interface TabItem<T extends string> {
  value: T
  label: ReactNode
}

interface TabsProps<T extends string> {
  label: string
  tabs: readonly TabItem<T>[]
  value: T
  onChange: (value: T) => void
  children: ReactNode
}

/** Tabs with the WAI-ARIA pattern: arrow keys, Home and End move between tabs. The panel holds
 * the selected tab's content. */
export function Tabs<T extends string>({ label, tabs, value, onChange, children }: TabsProps<T>) {
  const id = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const index = Math.max(0, tabs.findIndex((tab) => tab.value === value))

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = tabs.length - 1
    const target =
      event.key === 'ArrowRight' ? (index === last ? 0 : index + 1)
      : event.key === 'ArrowLeft' ? (index === 0 ? last : index - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null
    if (target === null) return
    event.preventDefault()
    event.stopPropagation()
    onChange(tabs[target].value)
    refs.current[target]?.focus()
  }

  return (
    <div className="ui-tabs">
      <div role="tablist" aria-label={label} className="ui-tablist" onKeyDown={onKeyDown}>
        {tabs.map((tab, i) => (
          <button
            key={tab.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${tab.value}`}
            aria-selected={tab.value === value}
            aria-controls={`${id}-panel`}
            tabIndex={tab.value === value ? 0 : -1}
            className="ui-tab"
            onClick={() => onChange(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${value}`} className="ui-tabpanel">
        {children}
      </div>
    </div>
  )
}
