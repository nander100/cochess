/** A message to show for a failed call: our ApiErrors are written to be read by players. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

/** The token in a login link's `#token=…` fragment, if any. */
export function tokenFromHash(hash: string): string | null {
  const token = new URLSearchParams(hash.replace(/^#/, '')).get('token')
  return token?.trim() || null
}
