import type { SlotCount } from '../api/types'
import { SLOT_HEADING } from './labels'

/** The 12-slot checklist (SPEC_V2 §10.3 step 2): "Wins as White 2/3", ... */
export function SlotChecklist({ slots }: { slots: readonly SlotCount[] }) {
  return (
    <ul className="slot-checklist" aria-label="Games needed">
      {slots.map(({ slot, filled, of }) => (
        <li key={slot} className={filled >= of ? 'full' : undefined}>
          <span className="slot-name">{SLOT_HEADING[slot]}</span>
          <span className="slot-count">
            {filled}/{of}
          </span>
        </li>
      ))}
    </ul>
  )
}
