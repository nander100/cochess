import type { MomentInfo } from '../api/types'

/** Not yet solved or revealed: the answer is still withheld. */
export function isUnsolved(moment: MomentInfo): boolean {
  return moment.state !== 'solved' && moment.state !== 'revealed'
}

/** A move with its number, as the coach writes it: "12. Nf3", "12... Nf6". */
export function numbered(moment: Pick<MomentInfo, 'move_number' | 'side'>, san: string): string {
  return `${moment.move_number}${moment.side === 'white' ? '.' : '...'} ${san}`
}
