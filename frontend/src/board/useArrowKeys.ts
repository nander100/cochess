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

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
