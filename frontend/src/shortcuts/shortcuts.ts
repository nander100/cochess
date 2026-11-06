/** Keyboard shortcuts (SPEC_V3 §4.4). */
export type ShortcutId =
  | 'prev'
  | 'next'
  | 'start'
  | 'end'
  | 'flip'
  | 'engine'
  | 'explain'
  | 'walk'
  | 'pause'
  | 'nextMoment'
  | 'escape'
  | 'focusChat'
  | 'help'

export interface Shortcut {
  id: ShortcutId
  /** As shown to the player. */
  keys: readonly string[]
  label: string
}

export const SHORTCUTS: readonly Shortcut[] = [
  { id: 'prev', keys: ['←'], label: 'Previous move' },
  { id: 'next', keys: ['→'], label: 'Next move' },
  { id: 'start', keys: ['↑', 'Home'], label: 'Start of the game' },
  { id: 'end', keys: ['↓', 'End'], label: 'End of the game (or of the variation)' },
  { id: 'flip', keys: ['F'], label: 'Flip the board' },
  { id: 'engine', keys: ['E'], label: 'Turn the engine panel on or off (not during an unsolved moment)' },
  { id: 'explain', keys: ['X'], label: 'Explain this position (not during an unsolved moment)' },
  { id: 'walk', keys: ['W'], label: "Walk through the engine's top line from this position" },
  { id: 'pause', keys: ['Space'], label: 'Pause or resume a line playing on the board' },
  { id: 'nextMoment', keys: ['N'], label: 'Next critical moment' },
  { id: 'escape', keys: ['Esc'], label: 'Close a dialog' },
  { id: 'focusChat', keys: ['/'], label: 'Type a question to the coach' },
  { id: 'help', keys: ['?'], label: 'Show these shortcuts' },
]

const BY_KEY: Record<string, ShortcutId> = {
  ArrowLeft: 'prev',
  ArrowRight: 'next',
  ArrowUp: 'start',
  Home: 'start',
  ArrowDown: 'end',
  End: 'end',
  f: 'flip',
  F: 'flip',
  e: 'engine',
  E: 'engine',
  x: 'explain',
  X: 'explain',
  w: 'walk',
  W: 'walk',
  ' ': 'pause',
  n: 'nextMoment',
  N: 'nextMoment',
  Escape: 'escape',
  '/': 'focusChat',
  '?': 'help',
}

/** The shortcut a key press means, or null: none while typing or with Ctrl, Alt or Cmd held. */
export function shortcutFor(event: Pick<KeyboardEvent, 'key' | 'altKey' | 'ctrlKey' | 'metaKey' | 'target'>): ShortcutId | null {
  if (event.altKey || event.ctrlKey || event.metaKey) return null
  const id = BY_KEY[event.key] ?? null
  if (id === null) return null
  // Esc still works from a text field (to leave it); everything else waits until typing stops.
  if (id !== 'escape' && isTyping(event.target)) return null
  return id
}

// Inputs where keys type text. Checkboxes, radios and buttons don't: arrow keys keep stepping
// through moves right after the player ticks the engine switch.
const TEXT_INPUTS = new Set(['text', 'search', 'number', 'email', 'password', 'url', 'tel'])

export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return true
  return target instanceof HTMLInputElement && TEXT_INPUTS.has(target.type)
}
