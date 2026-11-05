import type { SlotCount } from '../api/types'
import { SLOT_HEADING } from './labels'
import './Onboarding.css'

/** The 12 slots (SPEC_V2 §10.3 step 2) as the design's slot cards: color swatch, name, count, and
 * one cell per game. A full slot is tinted. */
export function SlotChecklist({ slots }: { slots: readonly SlotCount[] }) {
  return (
    <ul className="slot-checklist" aria-label="Games needed">
      {slots.map(({ slot, filled, of }) => (
        <li key={slot} className={filled >= of ? 'slot-card full' : 'slot-card'}>
          <div className="slot-head">
            <span aria-hidden="true" className={`slot-swatch ${slot.startsWith('white') ? 'white' : 'black'}`} />
            <span className="slot-name">{SLOT_HEADING[slot]}</span>
            <span className="slot-count">
              {filled}/{of}
            </span>
          </div>
          <div className="slot-cells" role="img" aria-label={`${SLOT_HEADING[slot]}: ${filled} of ${of} filled`}>
            {Array.from({ length: of }, (_, i) => (
              <span key={i} className={i < filled ? 'filled' : undefined} />
            ))}
          </div>
        </li>
      ))}
    </ul>
  )
}
