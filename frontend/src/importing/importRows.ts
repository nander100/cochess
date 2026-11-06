import type { Color, CreateGameRequest, ImportRow, Platform } from '../api/types'

/** What the player decides for one imported game: add it or not, and the color they played. */
export interface ImportChoice {
  include: boolean
  color: Color | null
}

export const PLATFORM_LABEL: Record<Platform, string> = { lichess: 'Lichess', chesscom: 'Chess.com' }

/** A game that can be added at all: it parsed, and it isn't one of the player's games already. */
export function addable(row: ImportRow): boolean {
  return row.pgn !== null && row.error === null && !row.already_imported
}

/** New games start ticked, with the color their username gave (or none: the player picks). */
export function initialChoices(rows: readonly ImportRow[]): ImportChoice[] {
  return rows.map((row) => ({ include: addable(row), color: row.user_color }))
}

/** Ticked games that still need a color before they can be added. */
export function missingColors(rows: readonly ImportRow[], choices: readonly ImportChoice[]): number {
  return rows.filter((row, i) => addable(row) && choices[i]?.include && choices[i]?.color === null).length
}

/** The uploads for the ticked games, each carrying its platform id so it's never added twice. */
export function requestsFor(rows: readonly ImportRow[], choices: readonly ImportChoice[]): CreateGameRequest[] {
  return rows.flatMap((row, i) => {
    const choice = choices[i]
    if (!addable(row) || row.pgn === null || !choice?.include || choice.color === null) return []
    return [
      {
        pgn: row.pgn,
        user_color: choice.color,
        external: { platform: row.platform, external_id: row.external_id },
      },
    ]
  })
}
