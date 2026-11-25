/** A message to show for a failed call: our ApiErrors are written to be read by players. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

/** The token in a login link's `#token=…` fragment, if any. */
export function tokenFromHash(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, '')).get('token')
  return token?.trim() || null
}

/** A game's date. PGN dates are UTC dates, so they're shown in UTC: a game dated 2026.01.01 is
 * stored as midnight UTC, and the local timezone would otherwise show the day before. */
export function gameDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium', timeZone: 'UTC' })
}

/** Coaching credits as players read them: whole numbers plain, others to one decimal. */
export function formatCredits(credits: number): string {
  return Number.isInteger(credits) ? String(credits) : credits.toFixed(1)
}

const REVOKE_AFTER_MS = 1000

/** Save `blob` as a download named `filename` (a PGN, the data export). */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS) // some browsers read it after click()
}
