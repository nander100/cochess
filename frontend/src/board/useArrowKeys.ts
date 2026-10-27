import { useEffect } from 'react'

/** ← and → step back and forward (SPEC_V2 §5.3), unless the player is typing somewhere. */
export function useArrowKeys(onBack: () => void, onForward: () => void): void {
  useEffect(() => {
    function handle(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) return
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        onBack()
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        onForward()
      }
    }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [onBack, onForward])
}

// Inputs where ← and → move a text cursor. Checkboxes, radios and buttons don't: arrow keys keep
// stepping through moves right after the player ticks the engine toggle.
const TEXT_INPUTS = new Set(['text', 'search', 'number', 'email', 'password', 'url', 'tel'])

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return true
  return target instanceof HTMLInputElement && TEXT_INPUTS.has(target.type)
}
