import type { Category, ParsedRow, Slot, TimeControl } from '../api/types'

export const SLOT_LABEL: Record<Slot, string> = {
  white_win: 'White win',
  white_loss: 'White loss',
  black_win: 'Black win',
  black_loss: 'Black loss',
}

export const SLOT_HEADING: Record<Slot, string> = {
  white_win: 'Wins as White',
  white_loss: 'Losses as White',
  black_win: 'Wins as Black',
  black_loss: 'Losses as Black',
}

export const CATEGORY_LABEL: Record<Category, string> = {
  bullet: 'Bullet',
  blitz: 'Blitz',
  rapid: 'Rapid',
  classical: 'Classical',
  correspondence: 'Correspondence',
}

export const PICKABLE: TimeControl[] = ['bullet', 'blitz', 'rapid', 'classical']

/** Why a pasted game fills no slot, in words; null when it fills one. */
export function reasonText(row: ParsedRow, primary: TimeControl): string | null {
  switch (row.reason) {
    case null:
      return null
    case 'invalid_pgn':
      return row.error?.message ?? "This game can't be analyzed."
    case 'duplicate':
      return "You've already added this game."
    case 'needs_color':
      return 'Choose the side you played.'
    case 'needs_time_control':
      return 'Choose the time control.'
    case 'wrong_time_control':
      return `Not a ${CATEGORY_LABEL[primary].toLowerCase()} game (your main time control).`
    case 'unfinished':
      return 'The game has no result.'
    case 'draw':
      return "Draws don't fill a slot."
    case 'slot_full':
      return row.user_color && row.user_result && row.user_result !== 'draw'
        ? `${SLOT_HEADING[`${row.user_color}_${row.user_result}`]}: already 3.`
        : 'That slot is full.'
  }
}
