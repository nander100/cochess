/** A short, soft click for "Sounds on move" (SPEC_V3 §4.3), made with the Web Audio API so no
 * sound files ship. Does nothing where audio isn't available (tests, old browsers). */
let context: AudioContext | null = null

export function playMoveSound(): void {
  const Audio = typeof window !== 'undefined' ? window.AudioContext : undefined
  if (!Audio) return
  try {
    context ??= new Audio()
    const now = context.currentTime
    const tone = context.createOscillator()
    const gain = context.createGain()
    tone.type = 'triangle'
    tone.frequency.setValueAtTime(520, now)
    tone.frequency.exponentialRampToValueAtTime(220, now + 0.06)
    gain.gain.setValueAtTime(0.15, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08)
    tone.connect(gain).connect(context.destination)
    tone.start(now)
    tone.stop(now + 0.09)
  } catch {
    // Audio blocked (e.g. before any user gesture): stay silent.
  }
}
